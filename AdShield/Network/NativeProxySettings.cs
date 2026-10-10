using System.Runtime.InteropServices;

namespace AdShield.Network;

internal sealed record NativeProxyState(int Flags, string Server, string Bypass, string AutoConfig);
internal static class NativeProxySettings
{
    [StructLayout(LayoutKind.Explicit)] private struct Value
    {
        [FieldOffset(0)] internal int Number;
        [FieldOffset(0)] internal IntPtr Text;
        [FieldOffset(0)] internal long Time;
    }
    [StructLayout(LayoutKind.Sequential)] private struct Option { internal int Id; internal Value Data; }
    [StructLayout(LayoutKind.Sequential)] private struct Options { internal int Size; internal IntPtr Connection; internal int Count; internal int Error; internal IntPtr Values; }
    [DllImport("wininet.dll", EntryPoint = "InternetSetOptionW", SetLastError = true)] private static extern bool Set(IntPtr handle, int option, IntPtr buffer, int length);
    [DllImport("wininet.dll", EntryPoint = "InternetQueryOptionW", SetLastError = true)] private static extern bool Query(IntPtr handle, int option, IntPtr buffer, ref int length);
    [DllImport("kernel32.dll")] private static extern IntPtr GlobalFree(IntPtr memory);

    internal static NativeProxyState Read()
    {
        int size = Marshal.SizeOf<Option>(); IntPtr data = Marshal.AllocHGlobal(size * 4), list = Marshal.AllocHGlobal(Marshal.SizeOf<Options>());
        bool queried = false;
        try
        {
            for (int i = 0; i < 4; i++) Marshal.StructureToPtr(new Option { Id = i + 1 }, data + i * size, false);
            var options = new Options { Size = Marshal.SizeOf<Options>(), Count = 4, Values = data }; Marshal.StructureToPtr(options, list, false);
            int length = options.Size;
            if (!Query(IntPtr.Zero, 75, list, ref length)) throw new InvalidOperationException("无法读取 Windows 当前连接的代理设置（错误 " + Marshal.GetLastWin32Error() + "）。");
            queried = true;
            Option At(int i) => Marshal.PtrToStructure<Option>(data + i * size);
            string Text(int i) => Marshal.PtrToStringUni(At(i).Data.Text) ?? "";
            return new(At(0).Data.Number, Text(1), Text(2), Text(3));
        }
        finally
        {
            if (queried) for (int i = 1; i < 4; i++) { var pointer = Marshal.PtrToStructure<Option>(data + i * size).Data.Text; if (pointer != IntPtr.Zero) GlobalFree(pointer); }
            Marshal.FreeHGlobal(data); Marshal.FreeHGlobal(list);
        }
    }
    internal static void Apply(NativeProxyState state)
    {
        int size = Marshal.SizeOf<Option>(); IntPtr data = Marshal.AllocHGlobal(size * 4), list = Marshal.AllocHGlobal(Marshal.SizeOf<Options>());
        var strings = new[] { Marshal.StringToHGlobalUni(state.Server), Marshal.StringToHGlobalUni(state.Bypass), Marshal.StringToHGlobalUni(state.AutoConfig) };
        try
        {
            Marshal.StructureToPtr(new Option { Id = 1, Data = new Value { Number = state.Flags } }, data, false);
            for (int i = 1; i < 4; i++) Marshal.StructureToPtr(new Option { Id = i + 1, Data = new Value { Text = strings[i - 1] } }, data + i * size, false);
            var options = new Options { Size = Marshal.SizeOf<Options>(), Count = 4, Values = data }; Marshal.StructureToPtr(options, list, false);
            if (!Set(IntPtr.Zero, 75, list, options.Size)) throw new InvalidOperationException("Windows 未接受系统代理设置（错误 " + Marshal.GetLastWin32Error() + "）。");
            Set(IntPtr.Zero, 95, IntPtr.Zero, 0); Set(IntPtr.Zero, 37, IntPtr.Zero, 0);
        }
        finally { foreach (var pointer in strings) Marshal.FreeHGlobal(pointer); Marshal.FreeHGlobal(data); Marshal.FreeHGlobal(list); }
    }
}
