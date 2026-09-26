/* Gold Promela: Peterson's two-process mutex (matches reference.py). */

bool flag0 = 0;
bool flag1 = 0;
byte turn = 0;
bool inCS0 = 0;
bool inCS1 = 0;

active proctype P0() {
  do
  :: flag0 = 1;
     turn = 1;
     (flag1 == 0 || turn == 0);
     inCS0 = 1;
     inCS0 = 0;
     flag0 = 0
  od
}

active proctype P1() {
  do
  :: flag1 = 1;
     turn = 0;
     (flag0 == 0 || turn == 1);
     inCS1 = 1;
     inCS1 = 0;
     flag1 = 0
  od
}

ltl mutex { [] !(inCS0 && inCS1) }
ltl starve0 { [] (flag0 -> <> inCS0) }
ltl starve1 { [] (flag1 -> <> inCS1) }
