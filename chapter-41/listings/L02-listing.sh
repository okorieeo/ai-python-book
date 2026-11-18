python -m ai_verify mutate --project sample --module billing_math.py \
  --cmd "python -m pytest -x -q -p no:cacheprovider test_weak.py"

Mutation testing: billing_math.py
  mutants: 56   killed: 33   survived: 23   score: 59%   (14s)
  Survivors (a bug like this would pass your tests):
    line  19: 100 -> 101
    line  19: <= -> <
    line  21: 0 -> 1
    line  21: < -> <=
    line  23: 100 -> 101
    line  33: 1 -> 2
    line  33: < -> <=
    line  35: 0 -> 1
    line  35: < -> <=
    line  47: 1 -> 2
    line  47: < -> <=
    line  50: // -> *
    line  61: return None instead of the value
    line  62: < -> <=
    line  71: 0 -> 1
    line  73: 0 -> 1
    line  74: * -> //
    line  74: 2 -> 3
    line  74: * -> //
    line  74: + -> -
    line  74: 2 -> 3
    line  74: * -> //
    line  74: // -> *
