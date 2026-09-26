/* Gold Promela: TCP three-way handshake (RFC 9293), no half-open accept. */

mtype = { CLOSED, LISTEN, SYN_SENT, SYN_RECEIVED, ESTABLISHED }

mtype cstate = CLOSED;
mtype sstate = LISTEN;
bool client_accepted = 0;
bool server_accepted = 0;

active proctype Handshake() {
  /* Client SYN: CLOSED -> SYN_SENT */
  cstate == CLOSED;
  cstate = SYN_SENT;

  /* Server SYN-ACK: LISTEN -> SYN_RECEIVED (not ESTABLISHED) */
  sstate == LISTEN;
  sstate = SYN_RECEIVED;

  /* Application must not accept while the server is only SYN_RECEIVED. */
  assert(sstate != ESTABLISHED || cstate == ESTABLISHED);

  /* Client ACK: SYN_SENT -> ESTABLISHED */
  cstate == SYN_SENT;
  cstate = ESTABLISHED;

  /* Server on ACK: SYN_RECEIVED -> ESTABLISHED */
  sstate == SYN_RECEIVED;
  sstate = ESTABLISHED;

  client_accepted = 1;
  server_accepted = 1
}

ltl both_established_before_accept {
  [] (
    (client_accepted || server_accepted) ->
    (cstate == ESTABLISHED && sstate == ESTABLISHED)
  )
}

ltl no_server_established_alone {
  [] !(sstate == ESTABLISHED && cstate != ESTABLISHED)
}
