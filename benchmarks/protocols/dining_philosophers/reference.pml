/* Gold Promela: five philosophers, lower-numbered fork first. */

bool fork_[5];
bool eating[5];

init {
  byte k = 0;
  do
  :: k < 5 -> fork_[k] = 1; k++
  :: k >= 5 -> break
  od
}

active [5] proctype Philosopher() {
  byte i = _pid - 1;
  byte left = i;
  byte right;
  byte first, second;
  right = (i + 1) % 5;
  if
  :: left < right -> first = left; second = right
  :: else -> first = right; second = left
  fi
  do
  :: atomic { fork_[first] -> fork_[first] = 0 }
     atomic { fork_[second] -> fork_[second] = 0 }
     eating[i] = 1;
     eating[i] = 0;
     fork_[second] = 1;
     fork_[first] = 1
  od
}

/* A philosopher holds both forks only while eating; never two neighbors
   eating at once (they share a fork). */
ltl mutex_neighbors {
  [] !(
    (eating[0] && eating[1]) ||
    (eating[1] && eating[2]) ||
    (eating[2] && eating[3]) ||
    (eating[3] && eating[4]) ||
    (eating[4] && eating[0])
  )
}
