using System.Diagnostics;

namespace chess
{
    public partial class Form1 : Form
    {
        public Form1()
        {
            InitializeComponent();
            this.TopMost = true;
        }

        private void label2_Click(object sender, EventArgs e)
        {

        }

        private void label1_Click(object sender, EventArgs e)
        {

        }

        private void checkBox1_CheckedChanged(object sender, EventArgs e)
        {

        }
        private void checkBox1_Paint(object sender, PaintEventArgs e)
        {
            CheckBox cb = (CheckBox)sender;
            e.Graphics.Clear(cb.BackColor);

            Rectangle boxRect = new Rectangle(0, 0, 16, 16);
            ControlPaint.DrawCheckBox(e.Graphics, boxRect, cb.Checked ? ButtonState.Checked : ButtonState.Normal);

            if (cb.Checked)
            {
                using (Brush fillBrush = new SolidBrush(Color.MediumSeaGreen))
                {
                    e.Graphics.FillRectangle(fillBrush, boxRect);
                }
            }
            TextRenderer.DrawText(e.Graphics, cb.Text, cb.Font, new Point(20, 0), cb.ForeColor);
        }

        private void radioButton1_CheckedChanged(object sender, EventArgs e)
        {

        }

        private void label1_Click_1(object sender, EventArgs e)
        {

        }

        private void guna2TextBox1_TextChanged(object sender, EventArgs e)
        {

        }

        private void guna2HtmlLabel1_Click(object sender, EventArgs e)
        {

        }

        private void guna2GradientPanel1_Paint(object sender, PaintEventArgs e)
        {
            // Set the drag control's target to this panel
            guna2DragControl1.TargetControl = guna2GradientPanel1;
        }

        private void guna2HtmlLabel3_Click(object sender, EventArgs e)
        {

        }

        private void guna2HtmlLabel5_Click(object sender, EventArgs e)
        {

        }

        private void guna2Button1_Click(object sender, EventArgs e)
        {
            Application.Exit();
        }

        private void Form1_Load(object sender, EventArgs e)
        {

        }

        private void guna2HtmlLabel5_Click_1(object sender, EventArgs e)
        {

        }

        private void Form1_Load_1(object sender, EventArgs e)
        {
            // In Form1 constructor or Form1_Load
            statusLabel.Text = "status: off";
        }

        private void comboBox1_SelectedIndexChanged(object sender, EventArgs e)
        {

        }

        private void guna2HtmlLabel6_Click(object sender, EventArgs e)
        {

        }

private void guna2Button2_Click(object sender, EventArgs e)
{
    // Show the color dialog
    if (colorPicker.ShowDialog() == DialogResult.OK)
    {
        Color selectedColor = colorPicker.Color;

        // Update UI colors
        UpdateUIColors(selectedColor);

        // Update settings file
        UpdateSettingsFile();
    }
}

        private Process? pythonProcess; // Make it nullable
        private bool isRunning = false;
        private void guna2Button3_Click(object sender, EventArgs e)
        {
            if (isRunning)
            {
                // Stop the running process
                StopPythonProcess();
                guna2Button3.Text = "Start";
                isRunning = false;

                // Update status label to "Off"
                statusLabel.Text = "status: off";
            }
            else
            {
                try
                {
                    // Create initial settings file
                    UpdateSettingsFile();

                    // Get values from UI controls
                    bool isEnabled = enabledBtn.Checked;
                    string side = whiteSide.Checked ? "white" : "black";
                    int engineEloValue = int.Parse(engineElo.Text);
                    Color arrowColor = colorPicker.Color;

                    // Convert color to hex format for Python
                    string colorHex = $"#{arrowColor.R:X2}{arrowColor.G:X2}{arrowColor.B:X2}";

                    // Build arguments string - now include the settings file path
                    string arguments = $"--settings-file \"{settingsFilePath}\"";

                    // Get current directory for the Python script
                    string scriptPath = @"C:\Users\abajr\source\repos\chess\chess\chess_analyzer.py";

                    // Rest of the method remains the same...
                    ProcessStartInfo psi = new ProcessStartInfo
                    {
                        FileName = "python",
                        Arguments = $"\"{scriptPath}\" {arguments}",
                        UseShellExecute = false,
                        RedirectStandardOutput = true,
                        RedirectStandardError = true,
                        CreateNoWindow = true,
                        WorkingDirectory = Path.GetDirectoryName(scriptPath)
                    };

                    // Create a debug log for output
                    string logPath = Path.Combine(Path.GetDirectoryName(scriptPath), "chess_analyzer_debug.log");
                    using (StreamWriter logFile = new StreamWriter(logPath, true))
                    {
                        logFile.WriteLine($"[{DateTime.Now}] Starting with settings file: {settingsFilePath}");
                    }

                    // Start the process
                    pythonProcess = new Process { StartInfo = psi };
                    pythonProcess.EnableRaisingEvents = true;
                    pythonProcess.Exited += HandleProcessExit;

                    // Handle standard output and error
                    pythonProcess.OutputDataReceived += (s, args) =>
                    {
                        if (!string.IsNullOrEmpty(args.Data))
                        {
                            // Log all output to debug file
                            using (StreamWriter logFile = new StreamWriter(logPath, true))
                            {
                                logFile.WriteLine($"[{DateTime.Now}] OUTPUT: {args.Data}");
                            }

                            // Check if the output contains evaluation data
                            if (args.Data.Contains("EVAL:"))
                            {
                                string evalText = args.Data.Split("EVAL:")[1].Trim();
                                UpdateEvaluationLabel(evalText);
                            }

                            // Display in console
                            Console.WriteLine($"Python: {args.Data}");
                        }
                    };

                    pythonProcess.ErrorDataReceived += (s, args) =>
                    {
                        if (!string.IsNullOrEmpty(args.Data))
                        {
                            // Log errors to debug file
                            using (StreamWriter logFile = new StreamWriter(logPath, true))
                            {
                                logFile.WriteLine($"[{DateTime.Now}] ERROR: {args.Data}");
                            }
                            Console.WriteLine($"Error: {args.Data}");
                        }
                    };

                    pythonProcess.Start();
                    pythonProcess.BeginOutputReadLine();
                    pythonProcess.BeginErrorReadLine();

                    // Update UI to indicate script is running
                    guna2Button3.Text = "Stop";
                    isRunning = true;

                    // Update status label to "On" or "Paused" based on enabledBtn.Checked
                    statusLabel.Text = isEnabled ? "status: running" : "status: paused";
                }
                catch (Exception ex)
                {
                    // Error handling code remains the same...
                    string errorLogPath = Path.Combine(
                        Path.GetDirectoryName(@"C:\Users\abajr\source\repos\chess\chess\chess_analyzer.py"),
                        "chess_error.log");

                    using (StreamWriter errorLog = new StreamWriter(errorLogPath, true))
                    {
                        errorLog.WriteLine($"[{DateTime.Now}] ERROR: {ex.Message}");
                        errorLog.WriteLine($"Stack Trace: {ex.StackTrace}");
                        if (ex.InnerException != null)
                        {
                            errorLog.WriteLine($"Inner Exception: {ex.InnerException.Message}");
                        }
                    }

                    MessageBox.Show($"Error starting the chess analyzer: {ex.Message}", "Error",
                        MessageBoxButtons.OK, MessageBoxIcon.Error);

                    statusLabel.Text = "status: off";
                }
            }
        }

        private void UpdateEvaluationLabel(string evalText)
        {
            // Update the evaluation label on the UI thread
            if (InvokeRequired)
            {
                BeginInvoke(new Action<string>(UpdateEvaluationLabel), evalText);
                return;
            }

            try
            {
                // Update the evaluation text
                evalLabel.Text = evalText;

                // Parse the evaluation value
                double evalValue;
                if (double.TryParse(evalText.Replace("+", ""), out evalValue))
                {
                    // Update evaluation panel height based on value
                    // Assuming evalPanel is a Panel control

                    // Normalize the evaluation to a percentage (0-100%)
                    // Values between -5 and +5 will be scaled linearly
                    double normalizedEval = (evalValue + 5) / 10.0;
                    normalizedEval = Math.Max(0, Math.Min(1, normalizedEval)); // Clamp between 0 and 1

                    // Calculate height percentage
                    int panelHeight = evalPanel.Parent.Height;
                    int whiteHeight = (int)(normalizedEval * panelHeight);
                    int blackHeight = panelHeight - whiteHeight;

                    // Update panel dimensions
                    evalPanel.Height = whiteHeight;
                    evalPanel.Top = blackHeight;

                    // Set color based on advantage
                    if (evalValue > 0.2)
                        evalLabel.ForeColor = Color.Green;
                    else if (evalValue < -0.2)
                        evalLabel.ForeColor = Color.Red;
                    else
                        evalLabel.ForeColor = Color.Black; // Roughly equal position
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Error updating evaluation: {ex.Message}");
            }
        }

        private void StopPythonProcess()
        {
            if (pythonProcess != null && !pythonProcess.HasExited)
            {
                try
                {
                    pythonProcess.Kill();
                    pythonProcess.Dispose();
                    pythonProcess = null;
                }
                catch (Exception ex)
                {
                    MessageBox.Show($"Error stopping the process: {ex.Message}");
                }
            }
        }
        private void HandleProcessExit(object? sender, EventArgs e)
        {
            if (InvokeRequired)
            {
                BeginInvoke(new Action<object, EventArgs>(HandleProcessExit), sender, e);
                return;
            }
            int exitCode = 0;
            try
            {
                Process proc = sender as Process;
                if (proc != null)
                {
                    exitCode = proc.ExitCode;
                }
            }
            catch { }

            guna2Button3.Text = "Start";
            isRunning = false;

            string logPath = Path.Combine(
                Path.GetDirectoryName(@"C:\Users\abajr\source\repos\chess\chess\chess_analyzer.py"),
                "chess_analyzer_debug.log");

            using (StreamWriter logFile = new StreamWriter(logPath, true))
            {
                logFile.WriteLine($"[{DateTime.Now}] Process exited with code: {exitCode}");
            }

            MessageBox.Show($"The chess analyzer process has stopped unexpectedly (Exit code: {exitCode}).\nCheck the debug log for details.",
                            "Process Ended", MessageBoxButtons.OK, MessageBoxIcon.Information);
        }


        private void guna2HtmlLabel1_Click_1(object sender, EventArgs e)
        {
            // Set the drag
            guna2DragControl2.TargetControl = guna2HtmlLabel1;
        }

        private void engineElo_TextChanged(object sender, EventArgs e)
        {
            if (isRunning) UpdateSettingsFile();
        }

        private void guna2ImageButton1_Click(object sender, EventArgs e)
        {
            string url = "https://github.com";

            try
            {
                System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo
                {
                    FileName = url,
                    UseShellExecute = true
                });
            }
            catch (Exception ex)
            {
                MessageBox.Show($"Unable to open the link: {ex.Message}", "Error",
                                MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }
        private void enabledBtn_CheckedChanged(object sender, EventArgs e)
        {
            // Update settings file when enabled state changes
            if (isRunning)
            {
                UpdateSettingsFile();
                statusLabel.Text = enabledBtn.Checked ? "status: running" : "status: paused";
            }
        }


        private void UpdateUIColors(Color selectedColor)
        {
            // Apply color to UI elements
            guna2Button2.BorderColor = selectedColor;
            guna2HtmlLabel1.ForeColor = selectedColor;
            engineElo.BorderColor = selectedColor;
            whiteSide.CheckedState.FillColor = selectedColor;
            whiteSide.CheckedState.BorderColor = selectedColor;
            blackSide.CheckedState.FillColor = selectedColor;
            blackSide.CheckedState.BorderColor = selectedColor;
            enabledBtn.CheckedState.FillColor = selectedColor;
            enabledBtn.UncheckedState.FillColor = Color.FromArgb(100, selectedColor);
            enabledBtn.CheckedState.BorderColor = selectedColor;

        }
        private void statusLabel_Click(object sender, EventArgs e)
        {

        }
        private void whiteSide_CheckedChanged(object sender, EventArgs e)
        {
            if (isRunning) UpdateSettingsFile();
        }

        private void blackSide_CheckedChanged(object sender, EventArgs e)
        {
            if (isRunning) UpdateSettingsFile();
        }



        private string settingsFilePath = Path.Combine(
    Path.GetDirectoryName(@"C:\Users\abajr\source\repos\chess\chess\chess_analyzer.py"),
    "chess_settings.json");

        private void UpdateSettingsFile()
        {
            try
            {
                // Create settings object
                var settings = new
                {
                    enabled = enabledBtn.Checked,
                    side = whiteSide.Checked ? "white" : "black",
                    elo = int.Parse(engineElo.Text),
                    arrow_color = $"#{colorPicker.Color.R:X2}{colorPicker.Color.G:X2}{colorPicker.Color.B:X2}"
                };

                // Serialize to JSON and write to file
                string jsonSettings = System.Text.Json.JsonSerializer.Serialize(settings);
                File.WriteAllText(settingsFilePath, jsonSettings);
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Error updating settings file: {ex.Message}");
            }
        }


    }
}
