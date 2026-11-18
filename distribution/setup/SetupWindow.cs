using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading.Tasks;
using System.Windows.Forms;

sealed class SetupWindow : Form
{
    private static readonly Color Surface = Color.FromArgb(15, 17, 23);
    private static readonly Color Card = Color.FromArgb(24, 27, 36);
    private static readonly Color White = Color.FromArgb(246, 247, 251);
    private static readonly Color Muted = Color.FromArgb(181, 189, 207);
    private static readonly Color Accent = Color.FromArgb(171, 40, 105);
    private static readonly Color Mint = Color.FromArgb(128, 229, 185);

    private readonly Panel body, destinationPage, progressPage, readyPage;
    private readonly TextBox destination;
    private readonly Label notice, runningText, readyNotice;
    private readonly ProgressBar progress;
    private readonly Button install, openCamera;
    private readonly LinkLabel python, git;
    private bool running;
    private string installedFolder;

    [DllImport("dwmapi.dll")]
    private static extern int DwmSetWindowAttribute(IntPtr window, int attribute, ref int value, int size);

    internal SetupWindow()
    {
        Text = "Configuração do SMB Camera";
        Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
        Font = new Font("Segoe UI", 10);
        BackColor = Surface;
        ForeColor = White;
        ClientSize = new Size(704, 442);
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        StartPosition = FormStartPosition.CenterScreen;
        AutoScaleDimensions = new SizeF(96F, 96F);
        AutoScaleMode = AutoScaleMode.Dpi;

        var brand = new PictureBox { Bounds = new Rectangle(30, 22, 36, 36), SizeMode = PictureBoxSizeMode.Zoom };
        brand.Image = Icon.ToBitmap();
        Controls.Add(brand);
        LabelOn(this, "SMB Camera", 77, 21, 290, 39, 18, White, true);
        LabelOn(this, "BETA PARA WINDOWS", 512, 32, 159, 25, 9, Muted, false).TextAlign = ContentAlignment.TopRight;
        Controls.Add(new Panel { Bounds = new Rectangle(30, 77, 644, 1), BackColor = Color.FromArgb(48, 51, 65) });

        body = new Panel { Bounds = new Rectangle(30, 97, 644, 316) };
        Controls.Add(body);

        destinationPage = NewPage("Instalar SMB Camera", "Escolha onde guardar o painel e seus componentes.");
        var picker = new Panel { Bounds = new Rectangle(0, 97, 644, 95), BackColor = Card };
        destinationPage.Controls.Add(picker);
        LabelOn(picker, "Pasta de instalação", 16, 13, 590, 24, 10, White, true);
        destination = new TextBox {
            Bounds = new Rectangle(16, 47, 470, 28), BackColor = Surface, ForeColor = White,
            BorderStyle = BorderStyle.FixedSingle, Text = Setup.DefaultFolder
        };
        picker.Controls.Add(destination);
        ButtonOn(picker, "Escolher pasta", 503, 41, 124, false, Browse);
        notice = LabelOn(destinationPage, "", 0, 207, 640, 43, 10, Muted, false);
        python = LinkOn(destinationPage, "Obter Python", 0, 250, "https://www.python.org/downloads/windows/");
        git = LinkOn(destinationPage, "Obter Git", 123, 250, "https://gitforwindows.org/");
        python.Visible = git.Visible = false;
        install = ButtonOn(destinationPage, "Instalar", 451, 267, 193, true, BeginInstall);

        progressPage = NewPage("Preparando o painel", "Você pode acompanhar o progresso aqui.");
        runningText = LabelOn(progressPage, "", 0, 115, 640, 60, 12, White, true);
        progress = new ProgressBar {
            Bounds = new Rectangle(0, 187, 644, 8), Style = ProgressBarStyle.Marquee,
            MarqueeAnimationSpeed = 0
        };
        progressPage.Controls.Add(progress);

        readyPage = NewPage("SMB Camera pronto", "Abra o painel para conectar seu iPhone.");
        LabelOn(readyPage, "✓  Instalado neste usuário", 0, 99, 640, 28, 11, Mint, true);
        readyNotice = LabelOn(readyPage, "", 0, 136, 640, 55, 10, Muted, false);
        ButtonOn(readyPage, "Configurar OBS", 0, 267, 146, false,
            () => Open(() => Setup.OpenObs(installedFolder)));
        ButtonOn(readyPage, "Guia do iPhone", 157, 267, 149, false,
            () => Open(() => Process.Start(Path.Combine(installedFolder, "docs", "PRIMEIRO-USO.html"))));
        openCamera = ButtonOn(readyPage, "Abrir SMB Camera", 451, 267, 193, true,
            () => Open(() => Setup.OpenCamera(installedFolder)));

        FormClosing += delegate(object sender, FormClosingEventArgs e) { if (running) e.Cancel = true; };
        var known = Setup.FindInstallation();
        if (known == null) ShowPage(destinationPage, install);
        else Finish(known);
    }

    protected override void OnHandleCreated(EventArgs e)
    {
        base.OnHandleCreated(e);
        int enabled = 1;
        DwmSetWindowAttribute(Handle, 20, ref enabled, sizeof(int));
    }

    Panel NewPage(string title, string subtitle)
    {
        var page = new Panel { Dock = DockStyle.Fill };
        LabelOn(page, title, 0, 2, 644, 45, 25, White, true);
        LabelOn(page, subtitle, 0, 52, 644, 36, 11, Muted, false);
        body.Controls.Add(page);
        return page;
    }

    void ShowPage(Panel page, Button primary)
    {
        foreach (Control view in body.Controls) view.Visible = view == page;
        page.BringToFront();
        AcceptButton = primary;
        if (primary != null) ActiveControl = primary;
    }

    static Label LabelOn(Control parent, string value, int x, int y, int width, int height,
                         int size, Color color, bool bold)
    {
        var label = new Label {
            Text = value, Bounds = new Rectangle(x, y, width, height), ForeColor = color,
            Font = new Font("Segoe UI", size, bold ? FontStyle.Bold : FontStyle.Regular)
        };
        parent.Controls.Add(label);
        return label;
    }

    static Button ButtonOn(Control parent, string text, int x, int y, int width, bool primary, Action action)
    {
        var button = new Button {
            Text = text, Bounds = new Rectangle(x, y, width, 43), ForeColor = White,
            BackColor = primary ? Accent : Card, FlatStyle = FlatStyle.Flat,
            Font = new Font("Segoe UI", 10, FontStyle.Bold)
        };
        button.FlatAppearance.BorderColor = primary ? Accent : Color.FromArgb(57, 62, 77);
        button.FlatAppearance.MouseOverBackColor = primary ? Color.FromArgb(195, 52, 124) : Color.FromArgb(36, 41, 55);
        button.Click += delegate { action(); };
        parent.Controls.Add(button);
        return button;
    }

    void Browse()
    {
        using (var dialog = new FolderBrowserDialog())
        {
            dialog.Description = "Escolha uma pasta local para o SMB Camera.";
            if (dialog.ShowDialog(this) != DialogResult.OK) return;
            destination.Text = dialog.SelectedPath;
            if (Setup.IsPrepared(dialog.SelectedPath)) Finish(dialog.SelectedPath);
        }
    }

    LinkLabel LinkOn(Panel page, string text, int x, int y, string href)
    {
        var link = new LinkLabel {
            Text = text, Bounds = new Rectangle(x, y, 115, 25),
            LinkColor = Color.FromArgb(244, 142, 198), ActiveLinkColor = White
        };
        link.LinkClicked += delegate { Process.Start(href); };
        page.Controls.Add(link);
        return link;
    }

    void Open(Action action)
    {
        try { action(); }
        catch (Exception) { readyNotice.Text = "Não foi possível abrir. Verifique se a pasta instalada está acessível."; }
    }

    void ShowReady(string folder, string message)
    {
        installedFolder = folder;
        readyNotice.Text = message.Length == 0 ? "Encontre SMB Camera e SMB Camera - Configurar OBS no menu Iniciar." : message;
        ShowPage(readyPage, openCamera);
    }

    async void BeginInstall()
    {
        string folder = destination.Text.Trim();
        if (folder.Length == 0) { notice.Text = "Escolha a pasta de instalação."; return; }
        if (Setup.IsPrepared(folder)) { Finish(folder); return; }
        running = true;
        runningText.Text = "Verificando os pré-requisitos…";
        progress.MarqueeAnimationSpeed = 30;
        ShowPage(progressPage, null);
        try
        {
            await Task.Run(() => Setup.Install(folder,
                message => Invoke(new Action(() => runningText.Text = message))));
            Finish(Path.GetFullPath(folder));
        }
        catch (Exception error)
        {
            notice.Text = error.Message;
            python.Visible = git.Visible = error.Message.StartsWith("Instale ", StringComparison.Ordinal);
            ShowPage(destinationPage, install);
        }
        finally
        {
            running = false;
            progress.MarqueeAnimationSpeed = 0;
        }
    }

    void Finish(string folder)
    {
        var message = "";
        try { Setup.Remember(folder); }
        catch (Exception) { message = "Painel pronto. Confira os atalhos e use estes botões se precisar."; }
        ShowReady(folder, message);
    }
}
