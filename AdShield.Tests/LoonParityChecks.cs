using AdShield.Network;
using System.IO;
using System.Text.Json;

internal static class LoonParityChecks
{
    internal static async Task PureAsync(Action<bool, string> check)
    {
        var plugin = LoonPlugin.Parse("""
            #!name = Parameter and condition fixture
            [Argument]
            enabled = switch,true,tag=Enabled
            region = select,"CN","US",tag=Region
            amount = input,"2.5",type=number,tag=Amount
            [Rewrite]
            response if (${url} ~= /\/v1\// || ${url} ~= /\/v2\//) && ${response.status} == 200 && ${response.header['Content-Type']} ~= /application\/json/i then response.json.delete("ads") | response.header.set("X-Region", "${region}") | response.json.replace("data.value", ${amount})
            request if ${url} ~= /^https:\/\/old\.test\/item\/(\d+)/ as item && ${request.method} == "GET" then url.replace("https://new.test/product/${item.1}") | request.header.set("X-Item", "${item.1}")
            [Script]
            response if (${url} ~= /\/v1\// || ${url} ~= /\/v2\//) && ${response.status} == 200 then script("script.js", {${enabled}, ${region}, ${amount}}) with requires_body=true, timeout=5, tag="Fixture"
            generic then script("manual.js", {${region}}) with tag="Manual", timeout=1
            cron "*/2 * * * * *" then script("cron.js") with enable=${enabled}, timeout=1
            network-changed then script("network.js") with timeout=1
            [Remote Rule]
            https://example.test/ads.list,REJECT
            [MITM]
            hostname = *, -secure.example.test
            """, "https://example.test/plugin.lpx");
        check(plugin.Unsupported.Count == 0 && plugin.Parameters.Count == 3 && plugin.Scripts.Count == 4, "modern Loon conditions, parameters and four script types import together");
        check(plugin.RemoteRules.Single().Policy == "REJECT", "positional remote-rule policy is preserved");
        check(plugin.MatchesHost("api.example.test") && !plugin.MatchesHost("secure.example.test"), "MITM wildcard exclusions override positive host matches");
        var values = plugin.EffectiveParameters();
        check(values["enabled"] is true && values["region"] is "CN" && values["amount"] is 2.5d, "plugin defaults preserve Boolean, String and Number types");
        plugin.ProtectedParameterValues = ProxyProfile.Protect(JsonSerializer.Serialize(new { region = "US", amount = 3.25 }));
        check(plugin.EffectiveParameters()["region"] is "US" && plugin.EffectiveParameters()["amount"] is 3.25d, "encrypted saved parameters override declared defaults");
        var context = new SyntaxContext { Request = new("https://api.test/v1/data", "GET", new(StringComparer.OrdinalIgnoreCase), ""), Response = new("", "GET", new(StringComparer.OrdinalIgnoreCase) { ["content-type"] = "Application/JSON" }, "", 200) };
        var outcome = await PluginRewriteEngine.ApplyAsync(plugin, plugin.Rewrites[0], context, () => Task.FromResult("{\"ads\":[1],\"data\":{\"value\":0},\"video\":\"keep\"}"), _ => { });
        using (var json = JsonDocument.Parse(context.Response!.Body))
            check(outcome.BodyChanged && !json.RootElement.TryGetProperty("ads", out _) && json.RootElement.GetProperty("data").GetProperty("value").GetDouble() == 3.25 && json.RootElement.GetProperty("video").GetString() == "keep" && context.Response.Headers["X-Region"] == "US", "compound response conditions apply ordered JSON/header actions with typed parameters");
        context.Response = context.Response with { Status = 404 };
        check(!(await PluginRewriteEngine.ApplyAsync(plugin, plugin.Rewrites[0], context, () => throw new Exception("must not read body"), _ => { })).Matched, "failed status condition cannot buffer or rewrite a response");
        context.Request = new("https://old.test/item/42?x=1", "GET", new(StringComparer.OrdinalIgnoreCase) { ["Host"] = "old.test" }, ""); context.Response = null;
        await PluginRewriteEngine.ApplyAsync(plugin, plugin.Rewrites[1], context, () => throw new Exception(), _ => { });
        check(context.Request.Url == "https://new.test/product/42?x=1" && context.Request.Headers["Host"] == "new.test" && context.Request.Headers["X-Item"] == "42", "named URL captures replace only matched range and update Host");
        plugin.Scripts[0].Code = "$done({body:JSON.stringify({region:$argument.region,amount:$argument.amount,enabled:$argument.enabled,loon:typeof $loon,script:typeof $script.startTime})});";
        var result = PluginScriptRunner.Run(plugin, plugin.Scripts[0], context.Request, new("", "GET", new(), "{}"))!;
        using (var json = JsonDocument.Parse(result.Body!)) check(json.RootElement.GetProperty("region").GetString() == "US" && json.RootElement.GetProperty("amount").GetDouble() == 3.25 && json.RootElement.GetProperty("loon").GetString() == "string" && json.RootElement.GetProperty("script").GetString() == "object", "script environment uses object arguments, string loon identity and Date startTime");
        var badGuard = LoonPlugin.Parse("[Script]\nresponse if ${url} ~= /api/ || ${response.status} == 200 then script(\"x.js\")", "https://example.test/p.lpx");
        check(badGuard.Unsupported.Count > 0, "response scripts reject OR branches that bypass URL guard");
        check(LoonPlugin.Parse("[Rewrite]\nrequest if ${response.status} == 200 then request.header.set(\"x\",\"y\")", "fixture").Unsupported.Count > 0, "request rules cannot use nonexistent response state");
        check(LoonPlugin.Parse("[Rewrite]\nrequest if ${url} ~= /api/ as item || ${request.method} == \"GET\" then request.header.set(\"x\",\"${item.1}\")", "fixture").Unsupported.Count > 0, "optional named captures cannot be used as mandatory action parameters");
        var batch = LoonPlugin.Parse("[Rewrite]\nresponse if ${url} ~= /api/ then response.header.set([\"X-A\",\"X-B\"],[\"1\",\"2\"])", "fixture");
        var batchContext = new SyntaxContext { Request = new("https://test/api", "GET", new(), ""), Response = new("", "GET", new(StringComparer.OrdinalIgnoreCase), "") };
        await PluginRewriteEngine.ApplyAsync(batch, batch.Rewrites.Single(), batchContext, () => throw new Exception(), _ => { });
        check(batchContext.Response!.Headers["X-A"] == "1" && batchContext.Response.Headers["X-B"] == "2", "batch header actions keep argument pairing");
        check(LoonPlugin.Parse("[Rewrite]\nresponse if ${url} ~= /api/ then response.header.set([\"a\",\"b\"],[\"1\"])", "fixture").Unsupported.Count > 0, "mismatched batch arrays are rejected at import");
        var mixed = LoonPlugin.Parse("[Rewrite]\n^https://test/api response-header-add X-Order first\nresponse if ${url} ~= /api/ then response.header.set(\"X-Order\",\"second\")", "fixture");
        foreach (var rewrite in mixed.Rewrites) await PluginRewriteEngine.ApplyAsync(mixed, rewrite, batchContext, () => throw new Exception(), _ => { });
        check(batchContext.Response.Headers["X-Order"] == "second", "legacy and modern header rewrites preserve file order");
        var mock = LoonPlugin.Parse("""
            [Rewrite]
            response if ${url} ~= /api/ then response.header.set("X-Local", "yes") | response.body.mock("json", `{"ads":[]}`, 201)
            """, "fixture");
        var mockContext = new SyntaxContext { Request = new("https://test/api", "GET", new(), "") };
        var mockResult = await PluginRewriteEngine.ApplyAsync(mock, mock.Rewrites.Single(), mockContext, () => throw new Exception(), _ => { });
        check(mockResult.SyntheticBody != null && mockContext.Response!.Status == 201 && mockContext.Response.Headers["X-Local"] == "yes", "response mock supports preceding headers without reading upstream state");
        check(new PluginCron("*/5 * * * * *").Matches(new DateTime(2026, 10, 9, 12, 0, 10)) && !new PluginCron("*/5 * * * * *").Matches(new DateTime(2026, 10, 9, 12, 0, 11)), "six-field cron steps match exact seconds");
        check(new PluginCron("0 8 * * 1-5").Matches(new DateTime(2026, 10, 9, 8, 0, 0)) && !new PluginCron("0 8 * * 1-5").Matches(new DateTime(2026, 10, 10, 8, 0, 0)), "five-field cron respects weekday range");
        bool invalid = false; try { _ = new PluginCron("0 0 1-foo * *"); } catch { invalid = true; }
        check(invalid, "invalid cron range cannot silently change schedule");
        var helper = new LoonScript { Phase = "http-request", Code = "$done();", Timeout = 1 };
        check(PluginScriptRunner.Run(new LoonPlugin(), helper, context.Request, null)?.AbortRequest == true, "request done without result stops upstream request");
        helper.Code = "setInterval((a,b)=>$done({body:a+b}),10,'timer-', 'args');";
        check(PluginScriptRunner.Run(new LoonPlugin(), helper, context.Request, null)?.Body == "timer-args", "Loon one-shot setInterval forwards callback arguments");
    }

    internal static async Task TaskRuntimeAsync(Action<bool, string> check)
    {
        string? previous = ProxyProfile.TestDirectory;
        ProxyProfile.TestDirectory = Path.GetFullPath(Path.Combine("..", "task-integration-" + Guid.NewGuid().ToString("N"))); Directory.CreateDirectory(ProxyProfile.DirectoryPath);
        try
        {
            var plugin = LoonPlugin.Parse("""
                [Script]
                generic then script("manual.js") with timeout=1
                cron "* * * * * *" then script("clock.js") with timeout=1
                """, "https://example.test/plugin.lpx");
            plugin.Enabled = true;
            plugin.Scripts[0].Code = "$persistentStore.write(typeof $request,'manual');$done();";
            plugin.Scripts[1].Code = "$persistentStore.write(String(Number($persistentStore.read('ticks')||0)+1),'ticks');$done();";
            var records = new List<string>();
            using (var tasks = new PluginTasks(new[] { plugin }, message => { lock (records) records.Add(message); }))
            {
                tasks.Start(); await tasks.ExecuteAsync(plugin, plugin.Scripts[0]);
                plugin.Scripts[0].Code = "$done({body:$persistentStore.read('manual')});";
                check(PluginScriptRunner.Run(plugin, plugin.Scripts[0], null, null)?.Body == "undefined", "manual tasks have no fabricated HTTP request object");
                await Task.Delay(1300);
                plugin.Scripts[0].Code = "$done({body:$persistentStore.read('ticks')||'0'});";
                check(int.Parse(PluginScriptRunner.Run(plugin, plugin.Scripts[0], null, null)?.Body ?? "0") > 0, "cron scheduler actually executes script and persistent storage");
                plugin.Scripts[0].Code = "setTimeout(()=>{$persistentStore.write('bad','cancelled');$done();},800);";
                var pending = tasks.ExecuteAsync(plugin, plugin.Scripts[0]); tasks.Dispose(); await pending;
            }
            plugin.Scripts[0].Code = "$done({body:$persistentStore.read('cancelled')||'clean'});";
            check(PluginScriptRunner.Run(plugin, plugin.Scripts[0], null, null)?.Body == "clean", "stop cancels outstanding task before delayed side effect");
        }
        finally { ProxyProfile.TestDirectory = previous; }
    }
}
