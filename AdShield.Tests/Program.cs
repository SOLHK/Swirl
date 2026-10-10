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
if (args.Length == 1 && args[0] == "--subscription-only") { SubscriptionChecks.Pure(Check); await SubscriptionChecks.DownloadAsync(Check); await SubscriptionRouteChecks.RunAsync(Check); Console.WriteLine($"All {passed} subscription checks passed."); return; }
if (args.Length == 1 && args[0] == "--core-startup-only") { CoreStartupChecks.Pure(Check); await CoreStartupChecks.RunAsync(Check); Console.WriteLine($"All {passed} core startup checks passed."); return; }
if (args.Length == 1 && args[0] == "--native-proxy-only") { await NativeCaptureChecks.RunAsync(Check); Console.WriteLine($"All {passed} native capture checks passed."); return; }
if (args.Length == 2 && args[0] == "--render-swirl-ui") { DesktopChecks.Render(args[1], Check); return; }
if (args.Length == 1 && args[0] == "--node-selection-only") { NodeSelectionChecks.Pure(Check); await NodeSelectionChecks.IntegrationAsync(Check); Console.WriteLine($"All {passed} node selection checks passed."); return; }
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
