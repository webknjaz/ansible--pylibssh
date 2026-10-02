"""A proxy.py-based TCP relay in front of sshd."""

import pathlib

from proxy.common.flag import flags
from proxy.common.types import Readables, Writables
from proxy.core.base import BaseTcpTunnelHandler
from proxy.core.connection import TcpServerConnection


flags.add_argument(
    '--sshd-upstream-host',
    type=str,
    default=None,
    help='Hostname of the sshd to relay to.',
)
flags.add_argument(
    '--sshd-upstream-port',
    type=int,
    default=None,
    help='Port of the sshd to relay to.',
)
flags.add_argument(
    '--sshd-replies-paused-file',
    type=str,
    default=None,
    help='Sentinel file that, once it exists, pauses the sshd replies.',
)


class PausableSshdTunnelHandler(BaseTcpTunnelHandler):
    """Tunnel a TCP connection to sshd, optionally withholding its replies."""

    def initialize(self) -> None:
        """Connect to sshd right away since it speaks first."""
        super().initialize()
        self.upstream = TcpServerConnection(
            self.flags.sshd_upstream_host,
            self.flags.sshd_upstream_port,
        )
        self.upstream.connect()

    def handle_data(self, data: memoryview) -> None:
        """Queue the client bytes for sshd.

        :param data: Bytes received from the client.
        """
        self.upstream.queue(data)

    async def handle_events(
        self,
        readables: Readables,
        writables: Writables,
    ) -> bool:
        """Handle the ready sockets, skipping sshd's ones while paused.

        :param readables: Sockets ready for reading.
        :param writables: Sockets ready for writing.
        :returns: Whether to tear the tunnel down.
        """
        # NOTE: The sentinel is checked before every pass that may read
        # NOTE: from sshd, so replies to anything sent after it got
        # NOTE: created are never forwarded. Omitting sshd's socket from
        # NOTE: `get_events()` would not work: proxy.py never unregisters
        # NOTE: sockets that drop out of it.
        if pathlib.Path(self.flags.sshd_replies_paused_file).exists():
            upstream_fileno = self.upstream.connection.fileno()
            readables = [
                ready_sock
                for ready_sock in readables
                if ready_sock != upstream_fileno
            ]
        return await super().handle_events(readables, writables)
