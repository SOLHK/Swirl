using System.Drawing;
using System.IO;
using AdShield.Network;

int passed = 0;
void Check(bool value, string name)
{
    if (!value) throw new Exception("FAIL: " + name);
    passed++;
    Console.WriteLine("PASS: " + name);
}
if (args.Length == 1 && args[0] == "--script-runtime-only") { ScriptRuntimeChecks.Pure(Check); await ScriptRuntimeChecks.IntegrationAsync(Check); Console.WriteLine($"All {passed} script runtime checks passed."); return; }
if (args.Length == 1 && args[0] == "--subscription-only") { SubscriptionChecks.Pure(Check); await SubscriptionChecks.DownloadAsync(Check); Console.WriteLine($"All {passed} subscription checks passed."); return; }
SubscriptionChecks.Pure(Check);
await SubscriptionChecks.DownloadAsync(Check);
NetworkChecks.Pure(Check);
ScriptRuntimeChecks.Pure(Check);
SyncRoutingChecks.Run(Check);
await LoonParityChecks.PureAsync(Check);
if (args.Length == 1 && args[0] == "--network-tests")
{
    await SubscriptionChecks.IntegrationAsync(Check);
    await NetworkChecks.IntegrationAsync(Check);
    await CaptureChecks.RunAsync(Check);
    await LoonParityChecks.TaskRuntimeAsync(Check);
    await ScriptRuntimeChecks.IntegrationAsync(Check);
    await ProtocolConfigChecks.RunAsync(Check);
}
if (args.Length == 2 && args[0] == "--render-proxy-ui")
{
    Exception? renderError = null;
    var thread = new Thread(() =>
    {
        try
        {
            Application.SetHighDpiMode(HighDpiMode.PerMonitorV2);
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            using var form = new RenderForm
            {
                ClientSize = new Size(1280, 820), AutoScaleMode = AutoScaleMode.Dpi, AutoScaleDimensions = new SizeF(96, 96),
                StartPosition = FormStartPosition.Manual, Location = new Point(-20000, -20000),
                ShowInTaskbar = false, Font = new Font("Microsoft YaHei UI", 9)
            };
            using var panel = new ProxyPanel();
            form.Controls.Add(panel); form.Show(); Application.DoEvents();
            if (panel.Size != form.ClientSize) throw new Exception("The panel does not fill its host.");
            using var image = new Bitmap(form.ClientSize.Width, form.ClientSize.Height);
            panel.DrawToBitmap(image, form.ClientRectangle); image.Save(args[1]);
            var colors = new HashSet<int>();
            for (int y = 0; y < 600; y += 5) for (int x = 0; x < 1200; x += 5) colors.Add(image.GetPixel(x, y).ToArgb());
            if (colors.Count < 10) throw new Exception("UI render is blank.");
        }
        catch (Exception e) { renderError = e; }
    });
    thread.SetApartmentState(ApartmentState.STA); thread.Start(); thread.Join();
    if (renderError != null) throw renderError;
    Check(File.Exists(args[1]), "Swirl UI initializes and renders on Windows");
}
Console.WriteLine($"All {passed} Swirl checks passed.");

sealed class RenderForm : Form
{
    protected override bool ShowWithoutActivation => true;
}
