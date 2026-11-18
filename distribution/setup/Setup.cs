using System;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Reflection;
using System.Windows.Forms;

[assembly: AssemblyTitle("Instalador SMB Camera Beta")]
[assembly: AssemblyProduct("SMB Camera")]
[assembly: AssemblyCompany("SIMBAproduz")]

static class Setup
{
    [STAThread]
    static int Main(string[] args)
    {
        if (args.Length == 2 && args[0] == "--install")
        {
            try { Install(args[1], delegate {}); return 0; }
            catch (Exception error) { Console.Error.WriteLine(error.Message); return 1; }
        }
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        Application.Run(new SetupWindow());
        return 0;
    }

    static ProcessStartInfo Command(string executable, string arguments, string directory)
    {
        return new ProcessStartInfo(executable, arguments) {
            WorkingDirectory = directory, UseShellExecute = false, CreateNoWindow = true
        };
    }

    internal static void OpenTool(string folder, string executable, string arguments)
    {
        Process.Start(Command(Path.Combine(folder, executable), arguments, folder));
    }

    static readonly string LocalHome = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "SMB Camera");
    internal static readonly string DefaultFolder = Path.Combine(LocalHome, "Beta");
    static readonly string Receipt = Path.Combine(LocalHome, "installed-folder.txt");
    const string Python = @".venv\Scripts\pythonw.exe";
    const string CameraArgs = "-m ucs.desktop --decoder d3d11va --renderer gl --matting-backend nvidia --alpha-output";

    static string ObsArgs
    {
        get
        {
            var near = Path.GetDirectoryName(Application.ExecutablePath);
            return "tools/obs_setup.py --near \"" + near.TrimEnd('\\') + "\"";
        }
    }

    internal static bool IsPrepared(string folder)
    {
        try
        {
            if (String.IsNullOrWhiteSpace(folder) || !Path.IsPathRooted(folder) || new Uri(folder).IsUnc)
                return false;
            var required = new[] { Python, "MANIFEST.json", "ucs/desktop.py", "tools/obs_setup.py", "docs/PRIMEIRO-USO.html" };
            return required.All(path => File.Exists(Path.Combine(folder, path))) &&
                File.ReadLines(Path.Combine(folder, "preparacao.log")).Any(line => line.StartsWith("Pronto.", StringComparison.Ordinal));
        }
        catch (IOException) { return false; }
        catch (ArgumentException) { return false; }
        catch (UnauthorizedAccessException) { return false; }
        catch (UriFormatException) { return false; }
    }

    internal static string FindInstallation()
    {
        string remembered = null;
        try { if (File.Exists(Receipt)) remembered = File.ReadAllText(Receipt).Trim(); }
        catch (IOException) { }
        catch (UnauthorizedAccessException) { }
        return IsPrepared(remembered) ? remembered : IsPrepared(DefaultFolder) ? DefaultFolder : null;
    }

    internal static void OpenCamera(string folder)
    {
        OpenTool(folder, Python, CameraArgs);
    }

    internal static void OpenObs(string folder)
    {
        OpenTool(folder, Python, ObsArgs);
    }

    internal static void Remember(string folder)
    {
        if (!IsPrepared(folder)) throw new InvalidOperationException("A preparação ainda não concluiu.");
        Directory.CreateDirectory(LocalHome);
        File.WriteAllText(Receipt, folder);
        var programs = Environment.GetFolderPath(Environment.SpecialFolder.Programs);
        var shortcuts = Path.Combine(programs, "SMB Camera");
        Directory.CreateDirectory(shortcuts);
        dynamic shell = Activator.CreateInstance(Type.GetTypeFromProgID("WScript.Shell"));
        MakeShortcut(shell, shortcuts, "SMB Camera", folder, CameraArgs);
        MakeShortcut(shell, shortcuts, "SMB Camera - Configurar OBS", folder, ObsArgs);
    }

    static void MakeShortcut(dynamic shell, string directory, string name, string folder, string args)
    {
        dynamic shortcut = shell.CreateShortcut(Path.Combine(directory, name + ".lnk"));
        shortcut.TargetPath = Path.Combine(folder, Python);
        shortcut.Arguments = args;
        shortcut.WorkingDirectory = folder;
        shortcut.IconLocation = Path.Combine(folder, "ucs/assets/live-icon.ico");
        shortcut.Save();
    }

    internal static void Install(string directory, Action<string> progress)
    {
        string root = Path.GetFullPath(directory);
        if (root.StartsWith(@"\\") || new Uri(root).IsUnc)
            throw new InvalidOperationException("Escolha uma pasta local.");
        if (Directory.Exists(root) && Directory.EnumerateFileSystemEntries(root).Any())
            throw new InvalidOperationException("Escolha uma pasta vazia para esta instalação.");

        progress("Verificando Python 3.11 x64 e OpenSSL…");
        try
        {
            string check = "import struct,sys,tkinter; from pathlib import Path; from shutil import which; "
                + "sys.exit(0 if struct.calcsize('P') == 8 and (which('openssl') or "
                + "Path('C:/Program Files/Git/usr/bin/openssl.exe').is_file()) else 1)";
            using (var verifier = Process.Start(Command("py.exe", "-3.11 -c \"" + check + "\"", Environment.SystemDirectory)))
            {
                verifier.WaitForExit();
                if (verifier.ExitCode != 0)
                    throw new InvalidOperationException("Instale Python 3.11 x64 e Git for Windows pelos links abaixo.");
            }
        }
        catch (System.ComponentModel.Win32Exception)
        {
            throw new InvalidOperationException("Instale Python 3.11 x64 com o launcher py pelos links abaixo.");
        }

        progress("Copiando os arquivos do SMB Camera…");
        Directory.CreateDirectory(root);
        string prefix = root.TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
        using (var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("SMB.Camera.Windows.Beta"))
        using (var archive = new ZipArchive(stream, ZipArchiveMode.Read))
        {
            foreach (var entry in archive.Entries)
            {
                int separator = entry.FullName.IndexOf('/');
                if (separator < 0 || entry.Name.Length == 0) continue;
                string target = Path.GetFullPath(Path.Combine(root, entry.FullName.Substring(separator + 1)));
                if (!target.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
                    throw new InvalidDataException("O pacote SMB Camera tem um caminho inválido.");
                Directory.CreateDirectory(Path.GetDirectoryName(target));
                entry.ExtractToFile(target, false);
            }
        }

        progress("Preparando o painel e verificando as dependências…");
        string cmd = Path.Combine(Environment.SystemDirectory, "cmd.exe");
        var command = Command(cmd, "/d /c Preparar.cmd > preparacao.log 2>&1", root);
        command.EnvironmentVariables["SMB_CAMERA_NONINTERACTIVE"] = "1";
        using (var process = Process.Start(command))
        {
            process.WaitForExit();
            if (process.ExitCode != 0)
                throw new InvalidOperationException("A preparação falhou. Confira preparacao.log e tente em uma pasta vazia.");
        }
    }
}
