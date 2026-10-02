Option Explicit

Dim shell, fs, appFolder, appFile, python, launcher, command, launchError
Set shell = CreateObject("WScript.Shell")
Set fs = CreateObject("Scripting.FileSystemObject")
appFolder = fs.GetParentFolderName(WScript.ScriptFullName)
appFile = fs.BuildPath(appFolder, "rap_writer.py")

If Not fs.FileExists(appFile) Then
    MsgBox "Rap Writer could not find rap_writer.py. Keep this launcher in the same folder as the app.", vbExclamation, "Rap Writer"
    WScript.Quit 1
End If

python = ""
If Not fs.FileExists(python) Then python = ""
If python = "" Then python = FindInPythonFolders(shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python")
If python = "" Then python = FindInPythonFolders(shell.ExpandEnvironmentStrings("%ProgramFiles%"))
If python = "" Then python = FindInPythonFolders(shell.ExpandEnvironmentStrings("%ProgramFiles(x86)%"))
If python = "" Then python = FindOnPath("pythonw.exe")

launcher = False
If python = "" Then
    python = FindOnPath("pyw.exe")
    launcher = (python <> "")
End If
If python = "" Then
    python = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Launcher\pyw.exe"
    If Not fs.FileExists(python) Then python = ""
    launcher = (python <> "")
End If
If python = "" Then
    python = shell.ExpandEnvironmentStrings("%WINDIR%") & "\pyw.exe"
    If Not fs.FileExists(python) Then python = ""
    launcher = (python <> "")
End If
If python = "" Then
    python = FindOnPath("py.exe")
    launcher = (python <> "")
End If

If python = "" Then
    MsgBox "Rap Writer needs Python 3 with Tkinter. Install Python from python.org with Tcl/Tk support, then open this launcher again.", vbExclamation, "Rap Writer"
    WScript.Quit 1
End If

If Not launcher Then ConfigureTclTk python
command = Quote(python) & " "
If launcher Then command = command & "-3 "
command = command & Quote(appFile)
shell.CurrentDirectory = appFolder
On Error Resume Next
shell.Run command, 0, False
launchError = Err.Description
If Err.Number <> 0 Then
    MsgBox "Rap Writer could not start: " & launchError, vbExclamation, "Rap Writer"
    WScript.Quit 1
End If
On Error GoTo 0

Function Quote(value)
    Quote = Chr(34) & value & Chr(34)
End Function

Function FindOnPath(fileName)
    Dim folder, candidate
    FindOnPath = ""
    For Each folder In Split(shell.Environment("PROCESS")("PATH"), ";")
        folder = Replace(Trim(folder), Chr(34), "")
        If folder <> "" Then
            candidate = fs.BuildPath(shell.ExpandEnvironmentStrings(folder), fileName)
            If fs.FileExists(candidate) Then
                FindOnPath = candidate
                Exit Function
            End If
        End If
    Next
End Function

Function FindInPythonFolders(parentPath)
    Dim folder, candidate
    FindInPythonFolders = ""
    If Not fs.FolderExists(parentPath) Then Exit Function
    candidate = fs.BuildPath(parentPath, "pythonw.exe")
    If fs.FileExists(candidate) Then
        FindInPythonFolders = candidate
        Exit Function
    End If
    For Each folder In fs.GetFolder(parentPath).SubFolders
        If LCase(Left(folder.Name, 6)) = "python" Then
            candidate = fs.BuildPath(folder.Path, "pythonw.exe")
            If fs.FileExists(candidate) Then
                FindInPythonFolders = candidate
                Exit Function
            End If
        End If
    Next
End Function

Sub ConfigureTclTk(pythonPath)
    Dim tclRoot, folder
    tclRoot = fs.BuildPath(fs.GetParentFolderName(pythonPath), "tcl")
    If Not fs.FolderExists(tclRoot) Then Exit Sub
    For Each folder In fs.GetFolder(tclRoot).SubFolders
        If fs.FileExists(fs.BuildPath(folder.Path, "init.tcl")) Then
            shell.Environment("PROCESS")("TCL_LIBRARY") = folder.Path
        End If
        If fs.FileExists(fs.BuildPath(folder.Path, "tk.tcl")) Then
            shell.Environment("PROCESS")("TK_LIBRARY") = folder.Path
        End If
    Next
End Sub
