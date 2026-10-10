using System.Drawing;
using System.IO;
using AdShield.Network;

int passed = 0;
void IsolateCorePorts()
{
    using var mixed = new System.Net.Sockets.TcpListener(System.Net.IPAddress.Loopback, 0); mixed.Start();
    using var plugin = new System.Net.Sockets.TcpListener(System.Net.IPAddress.Loopback, 0); plugin.Start();
    using var controller = new System.Net.Sockets.TcpListener(System.Net.IPAddress.Loopback, 0); controller.Start();
    MihomoConfig.TestPorts = (((System.Net.IPEndPoint)mixed.LocalEndpoint).Port, ((System.Net.IPEndPoint)plugin.LocalEndpoint).Port, ((System.Net.IPEndPoint)controller.LocalEndpoint).Port);
}
void Check(bool value, string name)
{
    if (!value) throw new Exception("FAIL: " + name);
    passed++;
    Console.WriteLine("PASS: " + name);
}
if (args.Length == 1 && args[0] == "--script-runtime-only") { ScriptRuntimeChecks.Pure(Check); await ScriptRuntimeChecks.IntegrationAsync(Check); Console.WriteLine($"All {passed} script runtime checks passed."); return; }
if (args.Length == 1 && args[0] == "--subscription-only") { SubscriptionChecks.Pure(Check); await SubscriptionChecks.DownloadAsync(Check); await SubscriptionRouteChecks.RunAsync(Check); Console.WriteLine($"All {passed} subscription checks passed."); return; }
if (args.Length == 1 && args[0] == "--core-startup-only") { CoreStartupChecks.Pure(Check); await CoreStartupChecks.RunAsync(Check); Console.WriteLine($"All {passed} core startup checks passed."); return; }
if (args.Length == 1 && args[0] == "--native-proxy-only") { await NativeCaptureChecks.RunAsync(Check); Console.WriteLine($"All {passed} native capture checks passed."); return; }
if (args.Length == 2 && args[0] == "--render-swirl-ui") { DesktopChecks.Render(args[1], Check); return; }
if (args.Length == 1 && args[0] == "--node-selection-only") { NodeSelectionChecks.Pure(Check); IsolateCorePorts(); await NodeSelectionChecks.IntegrationAsync(Check); Console.WriteLine($"All {passed} node selection checks passed."); return; }
if (args.Length == 1 && args[0] == "--workspace-only") { WorkspaceChecks.Pure(Check); IsolateCorePorts(); await WorkspaceChecks.IntegrationAsync(Check); Console.WriteLine($"All {passed} workspace checks passed."); return; }
WorkspaceChecks.Pure(Check);
NodeSelectionChecks.Pure(Check);
await ConnectionHealthChecks.RunAsync(Check);
CoreStartupChecks.Pure(Check);
SubscriptionChecks.Pure(Check);
await SubscriptionChecks.DownloadAsync(Check);
await SubscriptionRouteChecks.RunAsync(Check);
NetworkChecks.Pure(Check);
ScriptRuntimeChecks.Pure(Check);
SyncRoutingChecks.Run(Check);
await LoonParityChecks.PureAsync(Check);
if (args.Length == 1 && args[0] == "--network-tests")
{
    IsolateCorePorts();
    await WorkspaceChecks.IntegrationAsync(Check);
    await NodeSelectionChecks.IntegrationAsync(Check);
    await SubscriptionChecks.IntegrationAsync(Check);
    await NetworkChecks.IntegrationAsync(Check);
    await CaptureChecks.RunAsync(Check);
    await LoonParityChecks.TaskRuntimeAsync(Check);
    await ScriptRuntimeChecks.IntegrationAsync(Check);
    await ProtocolConfigChecks.RunAsync(Check);
    await CoreStartupChecks.RunAsync(Check);
}
Console.WriteLine($"All {passed} Swirl checks passed.");
