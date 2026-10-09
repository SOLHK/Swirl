using System.Drawing.Drawing2D;

namespace AdShield.Network;

internal static class SwirlTheme
{
    private static readonly Lazy<Bitmap> Artwork = new(() =>
    {
        using var stream = typeof(SwirlTheme).Assembly.GetManifestResourceStream("Swirl.Icon.png") ?? throw new InvalidOperationException("缺少 Swirl 图标资源。");
        using var image = Image.FromStream(stream); return new Bitmap(image);
    });
    internal static readonly Color Canvas = Color.FromArgb(247, 247, 252);
    internal static readonly Color Sidebar = Color.FromArgb(237, 240, 249);
    internal static readonly Color Ink = Color.FromArgb(35, 39, 58);
    internal static readonly Color Muted = Color.FromArgb(121, 129, 151);
    internal static readonly Color Accent = Color.FromArgb(107, 107, 238);
    internal static readonly Color Line = Color.FromArgb(232, 234, 245);
    internal static Font Font(float size = 9, FontStyle style = FontStyle.Regular) => new("Microsoft YaHei UI", size, style);
    internal static GraphicsPath Round(RectangleF rect, float radius)
    {
        var path = new GraphicsPath();
        float d = Math.Min(radius * 2, Math.Min(rect.Width, rect.Height));
        path.AddArc(rect.X, rect.Y, d, d, 180, 90);
        path.AddArc(rect.Right - d, rect.Y, d, d, 270, 90);
        path.AddArc(rect.Right - d, rect.Bottom - d, d, d, 0, 90);
        path.AddArc(rect.X, rect.Bottom - d, d, d, 90, 90); path.CloseFigure(); return path;
    }
    internal static void Kite(Graphics g, RectangleF box)
    {
        var saved = g.Save(); g.InterpolationMode = InterpolationMode.HighQualityBicubic; g.PixelOffsetMode = PixelOffsetMode.HighQuality;
        g.DrawImage(Artwork.Value, box); g.Restore(saved);
    }
    internal static Icon CreateIcon()
    {
        using var stream = typeof(SwirlTheme).Assembly.GetManifestResourceStream("Swirl.Icon.ico") ?? throw new InvalidOperationException("缺少 Swirl 图标资源。");
        using var icon = new Icon(stream); return (Icon)icon.Clone();
    }
    internal static void Prepare(Control control)
    {
        control.ForeColor = Ink; control.Font = Font();
        if (control is TextBox text) { text.BorderStyle = BorderStyle.FixedSingle; text.BackColor = Color.FromArgb(251, 252, 255); if (!text.Multiline) text.Height = 32; }
        if (control is ComboBox combo) { combo.FlatStyle = FlatStyle.Flat; combo.BackColor = Color.FromArgb(251, 252, 255); combo.Height = 32; }
        if (control is CheckBox check) { check.Padding = new Padding(0, 6, 0, 6); check.Margin = new Padding(0, 2, 0, 2); check.BackColor = Color.Transparent; }
        if (control is Label) control.BackColor = Color.Transparent;
    }
}

internal sealed class SwirlButton : Button
{
    private bool hovered;
    [System.ComponentModel.DesignerSerializationVisibility(System.ComponentModel.DesignerSerializationVisibility.Hidden)]
    internal bool Primary { get; set; }
    internal SwirlButton()
    {
        FlatStyle = FlatStyle.Flat; FlatAppearance.BorderSize = 0; Height = 38;
        AutoSize = true; AutoSizeMode = AutoSizeMode.GrowAndShrink; MinimumSize = new Size(90, 38);
        Padding = new Padding(15, 7, 15, 7); Margin = new Padding(0, 3, 8, 3);
        Font = SwirlTheme.Font(9, FontStyle.Bold); Cursor = Cursors.Hand; BackColor = Color.Transparent;
        SetStyle(ControlStyles.UserPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.AllPaintingInWmPaint, true);
    }
    protected override void OnMouseEnter(EventArgs e) { hovered = true; Invalidate(); base.OnMouseEnter(e); }
    protected override void OnMouseLeave(EventArgs e) { hovered = false; Invalidate(); base.OnMouseLeave(e); }
    protected override void OnPaint(PaintEventArgs e)
    {
        e.Graphics.SmoothingMode = SmoothingMode.AntiAlias;
        using var path = SwirlTheme.Round(new RectangleF(0, 0, Width - 1, Height - 1), 10 * DeviceDpi / 96f);
        Color color = Primary ? hovered ? Color.FromArgb(91, 88, 222) : SwirlTheme.Accent : hovered ? Color.FromArgb(233, 233, 251) : Color.FromArgb(242, 243, 250);
        if (!Enabled) color = Color.FromArgb(238, 239, 246);
        using var fill = new SolidBrush(color); e.Graphics.FillPath(fill, path);
        TextRenderer.DrawText(e.Graphics, Text, Font, ClientRectangle, !Enabled ? SwirlTheme.Muted : Primary ? Color.White : SwirlTheme.Ink, TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter);
        if (Focused) { using var pen = new Pen(Color.FromArgb(170, 150, 150, 240)); e.Graphics.DrawPath(pen, path); }
    }
}

internal sealed class SwirlNav : Button
{
    [System.ComponentModel.DesignerSerializationVisibility(System.ComponentModel.DesignerSerializationVisibility.Hidden)]
    internal bool Selected { get; set; }
    [System.ComponentModel.DesignerSerializationVisibility(System.ComponentModel.DesignerSerializationVisibility.Hidden)]
    internal string Symbol { get; set; } = "◈";
    private bool hovered;
    internal SwirlNav()
    {
        Width = 200; Height = 44; Margin = new Padding(0, 2, 0, 2); Cursor = Cursors.Hand;
        Font = SwirlTheme.Font(10); FlatStyle = FlatStyle.Flat; FlatAppearance.BorderSize = 0;
        BackColor = SwirlTheme.Sidebar; TabStop = true;
        SetStyle(ControlStyles.UserPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.AllPaintingInWmPaint, true);
    }
    protected override void OnMouseEnter(EventArgs e) { hovered = true; Invalidate(); base.OnMouseEnter(e); }
    protected override void OnMouseLeave(EventArgs e) { hovered = false; Invalidate(); base.OnMouseLeave(e); }
    protected override void OnPaint(PaintEventArgs e)
    {
        e.Graphics.SmoothingMode = SmoothingMode.AntiAlias; e.Graphics.Clear(SwirlTheme.Sidebar);
        if (Selected || hovered)
        {
            using var path = SwirlTheme.Round(new RectangleF(0, 0, Width - 1, Height - 1), 11 * DeviceDpi / 96f);
            using var fill = new SolidBrush(Selected ? Color.FromArgb(255, 255, 255) : Color.FromArgb(242, 244, 251)); e.Graphics.FillPath(fill, path);
        }
        using var iconFont = new Font("Segoe UI Symbol", 14);
        float scale = DeviceDpi / 96f;
        TextRenderer.DrawText(e.Graphics, Symbol, iconFont, new Rectangle((int)(12 * scale), (int)(7 * scale), (int)(30 * scale), (int)(30 * scale)), Selected ? SwirlTheme.Accent : SwirlTheme.Muted, TextFormatFlags.VerticalCenter | TextFormatFlags.HorizontalCenter);
        TextRenderer.DrawText(e.Graphics, Text, Font, new Rectangle((int)(51 * scale), 0, Width - (int)(55 * scale), Height), Selected ? SwirlTheme.Ink : SwirlTheme.Muted, TextFormatFlags.VerticalCenter);
    }
}

internal sealed class SwirlCard : FlowLayoutPanel
{
    internal SwirlCard()
    {
        AutoSize = true; AutoSizeMode = AutoSizeMode.GrowAndShrink; FlowDirection = FlowDirection.TopDown; WrapContents = false;
        BackColor = SwirlTheme.Canvas; Padding = new Padding(24, 20, 24, 20); Margin = new Padding(0, 0, 0, 18);
        SetStyle(ControlStyles.UserPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.AllPaintingInWmPaint, true);
    }
    protected override void OnPaintBackground(PaintEventArgs e)
    {
        e.Graphics.Clear(SwirlTheme.Canvas); e.Graphics.SmoothingMode = SmoothingMode.AntiAlias;
        using var path = SwirlTheme.Round(new RectangleF(.5f, .5f, Width - 1, Height - 1), 20 * DeviceDpi / 96f);
        using var fill = new SolidBrush(Color.White); e.Graphics.FillPath(fill, path);
        using var pen = new Pen(Color.FromArgb(235, 236, 247)); e.Graphics.DrawPath(pen, path);
    }
}

internal sealed class SwirlBrand : Control
{
    internal SwirlBrand() { Width = 210; Height = 95; BackColor = SwirlTheme.Sidebar; }
    protected override void OnPaint(PaintEventArgs e)
    {
        float scale = DeviceDpi / 96f;
        SwirlTheme.Kite(e.Graphics, new RectangleF(3 * scale, 11 * scale, 62 * scale, 62 * scale));
        using var title = SwirlTheme.Font(21, FontStyle.Bold); using var tiny = SwirlTheme.Font(8);
        TextRenderer.DrawText(e.Graphics, "Swirl", title, new Point((int)(75 * scale), (int)(19 * scale)), SwirlTheme.Ink);
        TextRenderer.DrawText(e.Graphics, "让网络轻盈一点", tiny, new Point((int)(78 * scale), (int)(58 * scale)), SwirlTheme.Muted);
    }
}

internal sealed class SwirlHero : Panel
{
    internal SwirlHero() { Height = 204; Margin = new Padding(0, 0, 0, 18); BackColor = SwirlTheme.Canvas; DoubleBuffered = true; }
    protected override void OnPaintBackground(PaintEventArgs e)
    {
        var g = e.Graphics; g.Clear(SwirlTheme.Canvas); g.SmoothingMode = SmoothingMode.AntiAlias;
        float scale = DeviceDpi / 96f;
        using var path = SwirlTheme.Round(new RectangleF(.5f, .5f, Width - 1, Height - 1), 22 * scale);
        using var gradient = new LinearGradientBrush(ClientRectangle, Color.FromArgb(235, 239, 255), Color.FromArgb(244, 236, 254), 12);
        g.FillPath(gradient, path);
        using var orb = new SolidBrush(Color.FromArgb(70, Color.White));
        g.FillEllipse(orb, Width - 190 * scale, -62 * scale, 242 * scale, 242 * scale); g.FillEllipse(orb, Width - 250 * scale, 110 * scale, 190 * scale, 190 * scale);
        SwirlTheme.Kite(g, new RectangleF(Width - 181 * scale, 28 * scale, 147 * scale, 147 * scale));
    }
}

internal sealed class SwirlField : Panel
{
    private readonly TextBox field;
    private readonly Label? cue;
    private bool focused;
    private static readonly Color Fill = Color.FromArgb(250, 251, 255);
    internal SwirlField(TextBox field)
    {
        this.field = field;
        Width = field.Width; Height = field.Multiline ? field.Height + 24 : 42;
        Margin = new Padding(0, 3, 0, 8); BackColor = Color.Transparent; Padding = new Padding(12);
        SetStyle(ControlStyles.UserPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.AllPaintingInWmPaint | ControlStyles.SupportsTransparentBackColor, true);
        field.BorderStyle = BorderStyle.None; field.BackColor = Fill; field.Margin = Padding.Empty;
        Controls.Add(field);
        if (!field.Multiline && field.PlaceholderText.Length > 0)
        {
            cue = new Label { Text = field.PlaceholderText, ForeColor = SwirlTheme.Muted, BackColor = Fill, Font = field.Font, AutoEllipsis = true, TextAlign = ContentAlignment.MiddleLeft, Margin = Padding.Empty };
            field.PlaceholderText = ""; Controls.Add(cue); cue.BringToFront(); cue.Click += (_, _) => field.Focus();
            field.TextChanged += (_, _) => UpdateCue(); field.EnabledChanged += (_, _) => UpdateCue();
        }
        field.Enter += (_, _) => { focused = true; UpdateCue(); Invalidate(); }; field.Leave += (_, _) => { focused = false; UpdateCue(); Invalidate(); };
        Resize += (_, _) => PositionField(); PositionField();
    }
    private void PositionField()
    {
        if (field == null) return;
        int pad = (int)(12 * DeviceDpi / 96f);
        field.Width = Math.Max(20, Width - pad * 2);
        if (field.Multiline) { field.Location = new Point(pad, pad); field.Height = Math.Max(20, Height - pad * 2); }
        else field.Location = new Point(pad, Math.Max(0, (Height - field.PreferredHeight) / 2));
        if (cue != null) cue.Bounds = field.Bounds;
        UpdateCue();
    }
    private void UpdateCue() { if (cue != null) { cue.Visible = field.TextLength == 0 && !focused; cue.Enabled = field.Enabled; cue.BringToFront(); } }
    protected override void OnPaintBackground(PaintEventArgs e)
    {
        base.OnPaintBackground(e); e.Graphics.SmoothingMode = SmoothingMode.AntiAlias;
        using var path = SwirlTheme.Round(new RectangleF(.5f, .5f, Width - 1, Height - 1), 10 * DeviceDpi / 96f);
        using var brush = new SolidBrush(Fill); e.Graphics.FillPath(brush, path);
        using var pen = new Pen(focused ? Color.FromArgb(157, 149, 237) : SwirlTheme.Line); e.Graphics.DrawPath(pen, path);
    }
    protected override void OnDpiChangedAfterParent(EventArgs e) { base.OnDpiChangedAfterParent(e); PositionField(); }
}
