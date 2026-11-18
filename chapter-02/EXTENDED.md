# Chapter 2 — Setting Up Your Development Environment: extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## Terminal Basics › Useful shortcuts and ideas

- **Tab** autocompletes file and folder names. Use it constantly.
- **Up arrow** recalls previous commands; **Ctrl+R** searches your command history.
- **Ctrl+C** stops a running program (for example a development server).
- **Pipes**: `ls | grep ".py"` sends the output of one command into another.
- **Redirection**: `echo "hello" > file.txt` writes to a file; `>>` appends.
- **Environment variables**: `export NAME="value"` sets one for the current session; `echo $NAME` prints it.
- **Permissions**: `chmod +x script.sh` makes a script executable; run it with `./script.sh`.
> **Dangerous command**
>
> Never run `rm -rf /` or `rm -rf *` unless you are completely sure where you are. Always check `pwd` first. AI assistants and tutorials sometimes suggest destructive commands; read each one before running it.


## Terminal Basics › Practice session

**terminal**

```bash
mkdir -p ~/projects/playground
cd ~/projects/playground
touch notes.txt
echo "My first terminal file" > notes.txt
cat notes.txt
cp notes.txt backup.txt
ls -la
rm backup.txt
cd ~
```


## Git and GitHub › Writing good commit messages

Commit messages are documentation for your future self. Use short, specific, present-tense messages:

**examples**

```
Good:  "Add JWT login endpoint"
Good:  "Fix crash when chat history is empty"
Bad:   "update"
Bad:   "stuff fixed final v2"
```


## VS Code › Useful settings and shortcuts

- Turn on **Format on Save** (Settings > search "format on save") so your code stays tidy automatically.
- **Ctrl+Backtick** opens the integrated terminal. **Ctrl+P** jumps to any file. **Ctrl+Shift+P** opens the command palette (run any command). **Ctrl+Shift+F** searches the whole project. **F2** renames a symbol everywhere. **F5** starts the debugger.
- Select the correct Python interpreter (`Ctrl+Shift+P` > "Python: Select Interpreter") and choose the one inside your project’s `.venv`.