# Installing Rubble

## One-Command Install (Windows)

Open **PowerShell as Administrator** and run:

```powershell
irm https://raw.githubusercontent.com/TM1988/Rubble/main/install.ps1 | iex
```

This will automatically:
- Install **Python 3.11** (if not already installed)
- Install **LLVM 18 / clang** (if not already installed)
- Clone the Rubble repository to `%LOCALAPPDATA%\Rubble`
- Install the `rubble` command globally
- Add everything to your PATH

After it finishes, **open a new terminal** and you're ready:

```
rubble main.rbl
```

---

## Manual Install

If you'd rather do it step by step:

### 1. Install Python 3.11+
Download from https://python.org/downloads  
**Important:** tick "Add Python to PATH" during install.

### 2. Install LLVM / clang
Download `LLVM-x.x.x-win64.exe` from:  
https://github.com/llvm/llvm-project/releases

During install, tick **"Add LLVM to the system PATH"**.

### 3. Clone Rubble
```powershell
git clone https://github.com/TM1988/Rubble.git
cd Rubble
```

### 4. Install the `rubble` command
```powershell
pip install -e .
```

### 5. Verify
Open a new terminal:
```
rubble examples\hello_world.rbl
```
Expected output: `Hello, World!`

---

## Updating Rubble

```powershell
cd %LOCALAPPDATA%\Rubble
git pull
pip install -e .
```

---

## Troubleshooting

**`rubble` is not recognized**  
→ Make sure Python's Scripts folder is on your PATH.  
→ Run `python -m compiler examples\hello_world.rbl` as a fallback.

**`clang` is not recognized**  
→ Add `C:\Program Files\LLVM\bin` to your PATH manually:  
  Settings → System → Environment Variables → Path → New

**Compile errors mentioning `.h` files**  
→ Make sure you have Visual Studio Build Tools installed, or install them with:  
```
winget install Microsoft.VisualStudio.2022.BuildTools
```

---

## Platform Support

| Platform | Status |
|----------|--------|
| Windows 10/11 | ✅ Full support |
| Linux | ✅ Compiler works, canvas stub only |
| macOS | ⚠️ Compiler works, canvas stub only |

Canvas (UI/graphics) on Linux/macOS will use X11/Metal backends in a future release.
