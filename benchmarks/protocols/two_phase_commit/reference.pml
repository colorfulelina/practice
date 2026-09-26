/* Gold Promela: two-phase commit, three participants (matches reference.py).

   Uninitialized mtype is 0. A named mtype constant is never 0 (SPIN starts
   those at 1), so `unset` has to be a #define. Otherwise pan treats empty
   outcome slots as already written and atomicity looks false. */

#define unset 0
mtype = { v_commit, v_abort, d_commit, d_abort }

mtype vote[3];
mtype outcome[3];
mtype decision;

active proctype Coordinator() {
  byte i = 0;
  do
  :: i < 3 && vote[i] != unset -> i++
  :: i == 3 -> break
  od
  if
  :: vote[0] == v_commit && vote[1] == v_commit && vote[2] == v_commit ->
        decision = d_commit
  :: else ->
        decision = d_abort
  fi
}

/* Coordinator is _pid 0; participants are 1, 2, 3. */
active [3] proctype Participant() {
  byte me = _pid - 1;
  if
  :: vote[me] = v_commit
  :: vote[me] = v_abort
  fi
  (decision != unset);
  outcome[me] = decision
}

ltl atomicity {
  [] (
    (outcome[0] != unset && outcome[1] != unset && outcome[2] != unset) ->
    (outcome[0] == outcome[1] && outcome[1] == outcome[2])
  )
}

ltl commit_only_if_all_yes {
  [] (
    (decision == d_commit) ->
    (vote[0] == v_commit && vote[1] == v_commit && vote[2] == v_commit)
  )
}
