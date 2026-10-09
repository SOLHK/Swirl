using System.Diagnostics;
using System.Runtime.InteropServices;

namespace AdShield.Network;

internal sealed class CoreProcessJob : IDisposable
{
    [StructLayout(LayoutKind.Sequential)] private struct BasicLimits
    {
        public long PerProcessTime, PerJobTime;
        public uint Flags;
        public UIntPtr MinWorkingSet, MaxWorkingSet;
        public uint ActiveProcesses;
        public UIntPtr Affinity;
        public uint Priority, Scheduling;
    }
    [StructLayout(LayoutKind.Sequential)] private struct IoCounters { public ulong ReadOps, WriteOps, OtherOps, ReadBytes, WriteBytes, OtherBytes; }
    [StructLayout(LayoutKind.Sequential)] private struct Limits
    {
        public BasicLimits Basic; public IoCounters Io;
        public UIntPtr ProcessMemory, JobMemory, PeakProcessMemory, PeakJobMemory;
    }
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)] private static extern IntPtr CreateJobObject(IntPtr attributes, string? name);
    [DllImport("kernel32.dll")] private static extern bool SetInformationJobObject(IntPtr job, int infoClass, ref Limits info, uint size);
    [DllImport("kernel32.dll")] private static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);
    [DllImport("kernel32.dll")] private static extern bool CloseHandle(IntPtr handle);
    private IntPtr handle;
    internal CoreProcessJob(Process process, ulong memoryLimit = 0)
    {
        handle = CreateJobObject(IntPtr.Zero, null);
        var limits = new Limits { Basic = new BasicLimits { Flags = 0x2000 | (memoryLimit > 0 ? 0x100u : 0u) }, ProcessMemory = (UIntPtr)memoryLimit };
        if (handle == IntPtr.Zero || !SetInformationJobObject(handle, 9, ref limits, (uint)Marshal.SizeOf<Limits>()) || !AssignProcessToJobObject(handle, process.Handle))
        {
            Dispose(); throw new InvalidOperationException("无法管理代理核心生命周期，未接管系统代理。");
        }
    }
    public void Dispose() { if (handle != IntPtr.Zero) { CloseHandle(handle); handle = IntPtr.Zero; } }
}
