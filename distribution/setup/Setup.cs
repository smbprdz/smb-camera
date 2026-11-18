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
