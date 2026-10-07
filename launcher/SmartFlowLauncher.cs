using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Windows.Forms;

[assembly: AssemblyTitle("SmartFlow AI")]
[assembly: AssemblyDescription("SmartFlow AI development launcher")]
[assembly: AssemblyCompany("SmartFlow AI")]
[assembly: AssemblyProduct("SmartFlow AI - AI Clip Creator")]
[assembly: AssemblyVersion("0.15.531.0")]
[assembly: AssemblyFileVersion("0.15.531.0")]

internal static class Program
{
    [STAThread]
    private static void Main()
    {
        string projectRoot = AppDomain.CurrentDomain.BaseDirectory.TrimEnd(
            Path.DirectorySeparatorChar,
            Path.AltDirectorySeparatorChar
        );
        string appPath = Path.Combine(projectRoot, "app.py");
        string pythonw = ResolvePythonw(projectRoot);

        if (!File.Exists(appPath))
        {
            MessageBox.Show(
                "ไม่พบ app.py กรุณาวาง SmartFlow AI.exe ไว้ในโฟลเดอร์โปรแกรมหลัก",
                "SmartFlow AI",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error
            );
            return;
        }

        if (!File.Exists(pythonw))
        {
            MessageBox.Show(
                "ไม่พบ Python สำหรับเปิด SmartFlow AI",
                "SmartFlow AI",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error
            );
            return;
        }

        try
        {
            Process.Start(new ProcessStartInfo
            {
                FileName = pythonw,
                Arguments = "\"" + appPath + "\"",
                WorkingDirectory = projectRoot,
                UseShellExecute = false,
                CreateNoWindow = true,
            });
        }
        catch (Exception error)
        {
            MessageBox.Show(
                "เปิด SmartFlow AI ไม่สำเร็จ\n\n" + error.Message,
                "SmartFlow AI",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error
            );
        }
    }

    private static string ResolvePythonw(string projectRoot)
    {
        string resolver = Path.Combine(projectRoot, "launcher", "resolve_python.ps1");
        if (!File.Exists(resolver))
        {
            return "";
        }

        string powershell = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.System),
            "WindowsPowerShell", "v1.0", "powershell.exe"
        );
        if (!File.Exists(powershell))
        {
            powershell = "powershell.exe";
        }

        try
        {
            using (Process resolverProcess = Process.Start(new ProcessStartInfo
            {
                FileName = powershell,
                Arguments = "-NoProfile -ExecutionPolicy Bypass -File \"" + resolver + "\"",
                WorkingDirectory = projectRoot,
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
            }))
            {
                if (resolverProcess == null || !resolverProcess.WaitForExit(10000))
                {
                    if (resolverProcess != null)
                    {
                        try { resolverProcess.Kill(); } catch { }
                    }
                    return "";
                }
                string candidate = resolverProcess.StandardOutput.ReadLine() ?? "";
                candidate = candidate.Trim();
                return resolverProcess.ExitCode == 0 && File.Exists(candidate) ? candidate : "";
            }
        }
        catch
        {
            return "";
        }
    }
}
