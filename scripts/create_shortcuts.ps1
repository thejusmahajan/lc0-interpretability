$WshShell = New-Object -ComObject WScript.Shell
$desktop = [System.Environment]::GetFolderPath('Desktop')
$pythonw = "C:\Users\Admin\miniconda3\envs\cszero\pythonw.exe"
$projectDir = "c:\Users\Admin\Documents\chess_speak_out_loud"

# Remove any old stop shortcuts
Remove-Item (Join-Path $desktop "Stop Knowledge Trainer.lnk") -ErrorAction SilentlyContinue
Remove-Item (Join-Path $desktop "Stop Chess Analysis.lnk") -ErrorAction SilentlyContinue
Remove-Item (Join-Path $desktop "Stop Chess Trainer.lnk") -ErrorAction SilentlyContinue

# 1. Knowledge Trainer Shortcut (Single .lnk app)
$trainerLnk = Join-Path $desktop "Knowledge Trainer.lnk"
$shortcutT = $WshShell.CreateShortcut($trainerLnk)
$shortcutT.TargetPath = $pythonw
$shortcutT.Arguments = "`"$projectDir\trainer\desktop_launcher.py`""
$shortcutT.WorkingDirectory = $projectDir
$shortcutT.Description = "Knowledge Trainer (Spaced Repetition Study Cards)"
$shortcutT.Save()

# 2. Chess Speak Out Loud Shortcut (Single .lnk app)
$chessLnk = Join-Path $desktop "Chess Speak Out Loud.lnk"
$shortcutC = $WshShell.CreateShortcut($chessLnk)
$shortcutC.TargetPath = $pythonw
$shortcutC.Arguments = "`"$projectDir\scripts\desktop_launcher_chess.py`""
$shortcutC.WorkingDirectory = $projectDir
$shortcutC.Description = "Chess Speak Out Loud (Neural Chess Analysis)"
$shortcutC.Save()

Write-Host "Configured single-click desktop apps:"
Write-Host "  -> $trainerLnk"
Write-Host "  -> $chessLnk"
