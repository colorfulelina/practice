/* Gold Promela: bounded buffer, capacity 4 (matches reference.py). */

#define N 4
byte count = 0;

active proctype Producer() {
  do
  :: count < N -> count = count + 1
  od
}

active proctype Consumer() {
  do
  :: count > 0 -> count = count - 1
  od
}

/* Guards keep 0 <= count <= N. Overflow-freedom is the safety claim. */
ltl no_overflow { [] (count <= N) }
