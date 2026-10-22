using AdShield.Network;


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
        new System.Windows.Application().Run(new Desktop.SwirlWindow());
    }
}
