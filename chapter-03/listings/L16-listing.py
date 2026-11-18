from pathlib import Path

path = Path("notes.txt")

path.write_text("Line one\nLine two\n", encoding="utf-8")      # write (overwrites)

print(path.read_text(encoding="utf-8"))                       # read everything

with open(path, "a", encoding="utf-8") as f:                  # "a" = append
    f.write("Line three\n")

with open(path, "r", encoding="utf-8") as f:
    for line in f:
        print(line.strip())

print(path.exists())
