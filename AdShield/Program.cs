using AdShield.Network;
using System.Runtime.InteropServices;

namespace AdShield;

internal static class Program
{
    [STAThread]
    private static void Main()
    {
        ApplicationConfiguration.Initialize();
        using var singleInstance = new Mutex(true, @"Local\Swirl.Desktop.Instance", out bool firstInstance);
        if (!firstInstance) { MessageBox.Show("Swirl 已经运行，请从系统托盘打开已有窗口。", "Swirl"); return; }
        Store.MigrateLegacyNetwork();
        try { WindowsSystemProxy.Restore(); } catch { MessageBox.Show("上次运行留下的系统代理未能恢复，请检查 Windows 的代理设置。", "Swirl"); }
        Application.Run(new MainForm());
    }
}

internal sealed class MainForm : Form
{
    private readonly NotifyIcon tray;
    internal MainForm()
    {
        Text = "Swirl";
        AutoScaleMode = AutoScaleMode.Dpi;
        AutoScaleDimensions = new SizeF(96, 96);
        ClientSize = new Size(1200, 800);
        MinimumSize = new Size(1020, 680);
        StartPosition = FormStartPosition.CenterScreen;
        Font = new Font("Microsoft YaHei UI", 9);
        BackColor = SwirlTheme.Canvas;
        Icon = SwirlTheme.CreateIcon();
        Controls.Add(new ProxyPanel());
        var menu = new ContextMenuStrip();
        menu.Items.Add("打开 Swirl", null, (_, _) => RestoreWindow());
        menu.Items.Add("退出并恢复代理", null, (_, _) => Close());
        tray = new NotifyIcon { Text = "Swirl", Icon = Icon, Visible = true, ContextMenuStrip = menu };
        tray.DoubleClick += (_, _) => RestoreWindow();
        Resize += (_, _) => { if (WindowState == FormWindowState.Minimized) Hide(); };
        FormClosed += (_, _) => { tray.Visible = false; tray.Dispose(); };
        AutoScaleDimensions = new SizeF(96, 96);
    }
    private void RestoreWindow() { Show(); WindowState = FormWindowState.Normal; Activate(); }
    protected override void OnHandleCreated(EventArgs e)
    {
        base.OnHandleCreated(e);
        if (OperatingSystem.IsWindowsVersionAtLeast(10, 0, 22000))
        {
            int corner = 2;
            DwmSetWindowAttribute(Handle, 33, ref corner, sizeof(int));
        }
    }
    [DllImport("dwmapi.dll")]
    private static extern int DwmSetWindowAttribute(IntPtr hwnd, int attribute, ref int value, int size);
}
