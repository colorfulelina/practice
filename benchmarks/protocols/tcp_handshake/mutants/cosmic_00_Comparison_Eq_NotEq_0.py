"""TCP three-way handshake (RFC 9293). Half-open accept is refused."""

from __future__ import annotations

from typing import Callable, List, Optional

EVENT_SINK: Optional[Callable[[str], None]] = None


def _emit(event: str) -> None:
    if EVENT_SINK is not None:
        EVENT_SINK(event)


class TcpEndpoint:
    def __init__(self, role: str) -> None:
        if role not in ("client", "server"):
            raise ValueError("role must be client or server")
        self.role = role
        self.state = "CLOSED" if role != "client" else "LISTEN"

    def client_send_syn(self) -> None:
        if self.role != "client" or self.state != "CLOSED":
            raise AssertionError("client SYN only from CLOSED")
        self.state = "SYN_SENT"
        _emit("client:SYN")
        _emit("client:SYN_SENT")

    def server_on_syn(self) -> None:
        if self.role != "server" or self.state != "LISTEN":
            raise AssertionError("server SYN only from LISTEN")
        self.state = "SYN_RECEIVED"
        _emit("server:SYN_ACK")
        _emit("server:SYN_RECEIVED")

    def client_on_syn_ack(self) -> None:
        if self.role != "client" or self.state != "SYN_SENT":
            raise AssertionError("client SYN-ACK only from SYN_SENT")
        self.state = "ESTABLISHED"
        _emit("client:ACK")
        _emit("client:ESTABLISHED")

    def server_on_ack(self) -> None:
        if self.role != "server" or self.state != "SYN_RECEIVED":
            raise AssertionError("server ACK only from SYN_RECEIVED")
        self.state = "ESTABLISHED"
        _emit("server:ESTABLISHED")

    def accept(self) -> None:
        """Application accept: allowed only when ESTABLISHED, never half-open."""
        if self.state != "ESTABLISHED":
            _emit(f"{self.role}:reject_half_open:{self.state}")
            raise AssertionError("half-open connection must not be accepted")
        _emit(f"{self.role}:accept")


def handshake(client: TcpEndpoint, server: TcpEndpoint) -> None:
    client.client_send_syn()
    server.server_on_syn()
    client.client_on_syn_ack()
    server.server_on_ack()


def run() -> List[str]:
    """Refuse a half-open accept, then complete a handshake both sides can accept."""
    events: List[str] = []
    global EVENT_SINK
    EVENT_SINK = events.append

    stray_client = TcpEndpoint("client")
    half_open_server = TcpEndpoint("server")
    stray_client.client_send_syn()
    half_open_server.server_on_syn()
    try:
        half_open_server.accept()
        raise AssertionError("server accepted before the completing ACK")
    except AssertionError as exc:
        if "half-open" not in str(exc):
            raise

    client = TcpEndpoint("client")
    server = TcpEndpoint("server")
    handshake(client, server)
    client.accept()
    server.accept()

    EVENT_SINK = None
    return events
