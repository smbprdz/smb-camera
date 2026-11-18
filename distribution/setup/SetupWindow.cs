using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Threading.Tasks;
using System.Windows.Forms;

sealed class SetupWindow : Form
{
    private static readonly Color Surface = Color.FromArgb(16, 18, 22);
    private static readonly Color Panel = Color.FromArgb(26, 29, 37);
    private static readonly Color TextColor = Color.FromArgb(239, 240, 246);
    private static readonly Color Muted = Color.FromArgb(177, 185, 203);
    private static readonly Color Accent = Color.FromArgb(181, 45, 115);

    private readonly TextBox destination;
    private readonly Label status;
    private readonly ProgressBar progress;
    private readonly Button install, choose, openCamera, openObs, openGuide;
    private readonly LinkLabel python, git;
    private bool running;
    private string installedFolder;

    internal SetupWindow()
    {
        Text = "Instalar SMB Camera Beta";
        Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
        Font = new Font("Segoe UI", 10);
        BackColor = Surface;
        ForeColor = TextColor;
        AutoScaleMode = AutoScaleMode.Dpi;
        ClientSize = new Size(690, 430);
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        StartPosition = FormStartPosition.CenterScreen;

        var mark = new PictureBox { Bounds = new Rectangle(24, 23, 52, 52), SizeMode = PictureBoxSizeMode.Zoom };
        mark.Image = Icon.ToBitmap();
        Controls.Add(mark);
        Controls.Add(Caption("SMB Camera", 88, 20, 570, 41, 26, FontStyle.Bold, TextColor));
        Controls.Add(Caption("Instalação beta para Windows · iPhone e OBS", 90, 63, 565, 30, 11, FontStyle.Regular, Muted));
        Controls.Add(Caption("Pasta de instalação", 28, 113, 615, 25, 11, FontStyle.Bold, TextColor));

        destination = new TextBox {
            Bounds = new Rectangle(28, 146, 497, 29), BackColor = Panel, ForeColor = TextColor,
            BorderStyle = BorderStyle.FixedSingle, Text = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "SMB Camera", "Beta")
        };
        Controls.Add(destination);
        choose = AddButton("Escolher…", 537, 139, 124, false, Browse);
        Controls.Add(Caption("O instalador prepara o painel. Depois, você escolhe o OBS para adicionar a fonte.",
                             28, 186, 630, 45, 10, FontStyle.Regular, Muted));

        progress = new ProgressBar { Bounds = new Rectangle(28, 238, 633, 7), Visible = false };
        Controls.Add(progress);
        status = Caption("Pronto para instalar no seu usuário.", 28, 255, 632, 56, 10, FontStyle.Bold, TextColor);
        Controls.Add(status);
        python = AddLink("Obter Python", 28, "https://www.python.org/downloads/windows/");
        git = AddLink("Obter Git", 151, "https://gitforwindows.org/");
        python.Visible = git.Visible = false;

        install = AddButton("Instalar SMB Camera", 431, 361, 230, true, BeginInstall);
        openCamera = AddButton("Abrir SMB Camera", 28, 361, 197, true,
            () => Open(() => Setup.OpenTool(installedFolder, @".venv\Scripts\pythonw.exe",
                "-m ucs.desktop --decoder d3d11va --renderer gl --matting-backend nvidia --alpha-output")));
        openObs = AddButton("Configurar OBS", 239, 361, 183, false,
            () => Open(() => Setup.OpenTool(installedFolder, @".venv\Scripts\pythonw.exe",
                "tools/obs_setup.py --near \"" + Path.GetDirectoryName(Application.ExecutablePath).TrimEnd('\\') + "\"")));
        openGuide = AddButton("Guia do iPhone", 436, 361, 225, false,
            () => Open(() => Process.Start(Path.Combine(installedFolder, "docs", "PRIMEIRO-USO.html"))));
        openCamera.Visible = openObs.Visible = openGuide.Visible = false;
        AcceptButton = install;
        FormClosing += delegate(object sender, FormClosingEventArgs e) { if (running) e.Cancel = true; };
    }

    static Label Caption(string value, int left, int top, int width, int height,
                         int size, FontStyle weight, Color color)
    {
        return new Label {
            Text = value, Bounds = new Rectangle(left, top, width, height),
            Font = new Font("Segoe UI", size, weight), ForeColor = color
        };
    }

    Button AddButton(string caption, int left, int top, int width, bool primary, Action action)
    {
        var button = new Button {
            Text = caption, Bounds = new Rectangle(left, top, width, 44),
            FlatStyle = FlatStyle.Flat, BackColor = primary ? Accent : Panel,
            ForeColor = TextColor, Font = new Font("Segoe UI", 10, FontStyle.Bold)
        };
        button.FlatAppearance.BorderColor = primary ? Accent : Color.FromArgb(55, 61, 75);
        button.Click += delegate { action(); };
        Controls.Add(button);
        return button;
    }

    LinkLabel AddLink(string caption, int left, string href)
    {
        var link = new LinkLabel {
            Text = caption, Bounds = new Rectangle(left, 318, 112, 25),
            LinkColor = Color.FromArgb(249, 155, 205), ActiveLinkColor = TextColor
        };
        link.LinkClicked += delegate { Open(() => Process.Start(href)); };
        Controls.Add(link);
        return link;
    }

    void Browse()
    {
        using (var chooser = new FolderBrowserDialog())
        {
            chooser.Description = "Escolha uma pasta vazia para instalar esta beta.";
            if (chooser.ShowDialog(this) == DialogResult.OK) destination.Text = chooser.SelectedPath;
        }
    }

    void Open(Action task)
    {
        try { task(); }
        catch (Exception) { status.Text = "Não consegui abrir esta etapa. Confira a pasta instalada."; }
    }

    async void BeginInstall()
    {
        string folder = destination.Text.Trim();
        if (folder.Length == 0) { status.Text = "Escolha a pasta de instalação."; return; }
        running = true;
        destination.Enabled = choose.Enabled = install.Enabled = false;
        python.Visible = git.Visible = false;
        progress.Visible = true;
        progress.Style = ProgressBarStyle.Marquee;
        try
        {
            await Task.Run(() => Setup.Install(folder, message => Invoke(new Action(() => status.Text = message))));
            installedFolder = Path.GetFullPath(folder);
            destination.Text = installedFolder;
            status.Text = "SMB Camera instalado. Abra o painel e configure a fonte no OBS.";
            install.Visible = false;
            openCamera.Visible = openObs.Visible = openGuide.Visible = true;
            AcceptButton = openCamera;
        }
        catch (Exception error)
        {
            status.Text = error.Message;
            python.Visible = git.Visible = error.Message.StartsWith("Instale ", StringComparison.Ordinal);
            destination.Enabled = choose.Enabled = install.Enabled = true;
        }
        finally { running = progress.Visible = false; }
    }
}
