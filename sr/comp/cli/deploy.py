import sys
import warnings
from contextlib import contextmanager
from typing import Any, Iterator, Optional, Sequence, Type

API_TIMEOUT_SECONDS = 3
SSH_TIMEOUT_SECONDS = 2
DEPLOY_USER = 'srcomp'
BOLD = '\033[1m'
FAIL = '\033[91m'
OKBLUE = '\033[94m'
ENDC = '\033[0m'


def ssh_connection(host):
    from paramiko import AutoAddPolicy, SSHClient

    client = SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(AutoAddPolicy())
    client.connect(host, username=DEPLOY_USER, timeout=SSH_TIMEOUT_SECONDS)
    return client


def format_fail(*args: object) -> str:
    msg = " ".join(map(str, args))
    return BOLD + FAIL + msg + ENDC


@contextmanager
def exit_on_exception(
    msg: str = '{0}',
    kind: Type[Exception] = Exception,
) -> Iterator[None]:
    try:
        yield
    except kind as e:
        print_fail(msg.format(e))
        exit(1)


@contextmanager
def guard_unicode_output(stream):
    """
    Cope with users environments not being able to handle unicode by softening
    the display of characters they can't handle.

    While I would ideally prefer not to have this sort of behaviour, as it can
    happen mid-deploy (which we cannot roll back) it's far safer that we handle
    these _somehow_ than error the deploy part-way through.

    This is aimed at users running under certain Windows Subsystem for Linux
    Operating Systems which default to a non utf-8 locale :(
    """

    encoding = stream.encoding

    if encoding.lower() == 'utf-8':
        # Happy path
        yield
        return

    warnings.warn(
        "Your locale does not support unicode. Some characters may not display correctly.",
    )

    orig_write = stream.write

    def write(text, *a, **k):
        text = text.encode(encoding, errors='backslashreplace').decode(encoding)
        orig_write(text, *a, **k)

    try:
        stream.write = write
        yield
    finally:
        stream.write = orig_write


def print_fail(*args: object, **kargs: Any) -> None:
    print(format_fail(*args), **kargs)


def print_buffer(buf):
    prefix = '> '
    print(prefix + prefix.join(buf.readlines()).strip())


def get_input(prompt: str) -> str:
    # Wrapper to simplify mocking
    return input(prompt)


def query(
    question: str,
    options: Sequence[str],
    default: Optional[str] = None,
) -> str:
    if default:
        assert default in options

    options = [o.upper() if o == default else o.lower() for o in options]
    assert len(set(options)) == len(options)
    opts = '/'.join(options)

    query = format_fail("{0} [{1}]: ".format(question.rstrip(), opts))

    while True:
        # Loop until we get a suitable response from the user
        resp = get_input(query).lower()

        if resp in options:
            return resp

        # If there's a default value, use that
        if default:
            return default


def query_bool(question: str, default_val: Optional[bool] = None) -> bool:
    options = ('y', 'n')
    if default_val is True:
        default = 'y'  # type: Optional[str]
    elif default_val is False:
        default = 'n'
    else:
        default = None
    return query(question, options, default) == 'y'


def query_warn(msg: object) -> None:
    query_msg = "Warning: {0}. Continue?".format(msg)
    if not query_bool(query_msg, False):
        exit(1)


def ref_compstate(host: str) -> str:
    url = 'ssh://{0}@{1}/~/compstate.git'.format(DEPLOY_USER, host)
    return url


def deploy_to(compstate, host, revision, verbose):
    print(BOLD + "Deploying to {0}:".format(host) + ENDC)

    # Make connection early to check if host is up.
    with ssh_connection(host) as client:
        # Push the repo
        url = ref_compstate(host)
        # Make a new branch for this revision so that it's visible to
        # anything which fetches the repo; use the revision id in the
        # branch name to avoid race conditions without needing to come
        # up with our own unique identifier.
        # This also means we don't need to worry about whether or not the
        # revision exists in the target, since this push will simply no-op
        # if it's already present
        revspec = '{0}:refs/heads/deploy-{0}'.format(revision)
        with exit_on_exception(kind=RuntimeError):
            compstate.push(
                url,
                revspec,
                err_msg="Failed to push to {0}.".format(host),
            )

        cmd = "./update '{0}'".format(revision)
        _, stdout, stderr = client.exec_command(cmd)
        retcode = stdout.channel.recv_exit_status()

        if verbose or retcode != 0:
            print_buffer(stdout)

        print_buffer(stderr)

        return retcode


def get_deployments(compstate):
    with exit_on_exception("Failed to get deployments from state ({0})."):
        return compstate.deployments


def get_current_state(host):
    import simplejson as json
    from urllib.request import urlopen

    url = 'http://{0}/comp-api/state'.format(host)
    try:
        page = urlopen(url, timeout=API_TIMEOUT_SECONDS)
        raw_state = json.load(page)
    except Exception as e:
        print(e)
        return None
    else:
        return raw_state['state']


def check_host_state(compstate, host, revision, verbose):
    """
    Compares the host state to the revision we want to deploy. If the
    host's state isn't in the history of the deploy revision then various
    options are presented to the user.

    Returrns whether or not to skip deploying to the host.
    """
    SKIP = True
    UPDATE = False
    if verbose:
        print("Checking host state for {0} (timeout {1} seconds).".format(
            host,
            API_TIMEOUT_SECONDS,
        ))
    state = get_current_state(host)
    if not state:
        tpl = "Failed to get state for {0}, cannot advise about history." \
              " Deploy anyway?"
        if query_bool(tpl.format(host, state), True):
            return UPDATE
        else:
            return SKIP

    if state == revision:
        print("Host {0} already has requested revision ({1})".format(
            host,
            revision[:8],
        ))
        return SKIP

    # Ideal case:
    if compstate.has_ancestor(state):
        return UPDATE

    # Check for unknown commit
    if not compstate.has_commit(state):
        tpl = "Host {0} has unknown state '{1}'. Try to fetch it?"
        if query_bool(tpl.format(host, state), True):
            compstate.fetch('origin', quiet=True)
            compstate.fetch(ref_compstate(host), quiet=True)

    # Old revision:
    if compstate.has_descendant(state):
        tpl = "Host {0} has more recent state '{1}'. Deploy anyway?"
        if query_bool(tpl.format(host, state), True):
            return UPDATE
        else:
            return SKIP

    # Some other revision:
    if compstate.has_commit(state):
        tpl = "Host {0} has sibling state '{1}'. Deploy anyway?"
        if query_bool(tpl.format(host, state), True):
            return UPDATE
        else:
            return SKIP

    # An unknown state
    tpl = "Host {0} has unknown state '{1}'. Deploy anyway?"
    if query_bool(tpl.format(host, state), True):
        return UPDATE
    else:
        return SKIP


def require_no_changes(compstate):
    if compstate.has_changes:
        print_fail(
            "Cannot deploy state with local changes.",
            "Commit or remove them and re-run.",
        )
        compstate.show_changes()
        exit(1)


def require_valid(compstate):
    from sr.comp.validation import validate

    with exit_on_exception("State cannot be loaded: {0}"):
        comp = compstate.load()

    num_errors = validate(comp)
    if num_errors:
        query_warn("State has validation errors (see above)")


def run_deployments(args, compstate, hosts):
    revision = compstate.rev_parse('HEAD')
    for host in hosts:
        if not args.skip_host_check:
            skip_host = check_host_state(compstate, host, revision, args.verbose)
            if skip_host:
                print(BOLD + "Skipping {0}.".format(host) + ENDC)
                continue

        retcode = deploy_to(compstate, host, revision, args.verbose)
        if retcode != 0:
            # TODO: work out if it makes sense to try to rollback here?
            print_fail("Failed to deploy to '{0}' (exit status: {1}).".format(
                host,
                retcode,
            ))
            exit(retcode)

    print(BOLD + OKBLUE + "Done" + ENDC)


def command(args):
    from sr.comp.raw_compstate import RawCompstate

    with guard_unicode_output(sys.stdout), guard_unicode_output(sys.stderr):
        compstate = RawCompstate(args.compstate, local_only=False)
        hosts = get_deployments(compstate)

        require_no_changes(compstate)
        require_valid(compstate)

        run_deployments(args, compstate, hosts)


def add_options(parser):
    parser.add_argument('--verbose', action='store_true')
    parser.add_argument(
        '--skip-host-check',
        action='store_true',
        help="skips checking the current state of the hosts",
    )


def add_subparser(subparsers):
    help_msg = "Deploy a given competition state to all known hosts"
    parser = subparsers.add_parser(
        'deploy',
        help=help_msg,
        description=help_msg,
    )
    add_options(parser)
    parser.add_argument('compstate', help="competition state repository")
    parser.set_defaults(func=command)
