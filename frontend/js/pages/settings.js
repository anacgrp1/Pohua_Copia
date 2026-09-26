/**
 * Settings Page
 */
const SettingsPage = {
    async render(container) {
        container.innerHTML = `
            <div style="max-width: 800px">
                <div class="detail-panel">
                    <div class="detail-panel-title">System Settings</div>
                    <p class="form-label" style="margin-bottom:20px;font-weight:400">This screen edits the backend environment variables (.env). Administrators only.</p>
                    
                    <div class="form-group">
                        <label class="form-label">Email Mode (MAIL_MODE)</label>
                        <select class="form-select" id="setMailMode">
                            <option value="imap">IMAP (Local)</option>
                            <option value="graph">Graph API (Token)</option>
                        </select>
                    </div>

                    <div class="form-group">
                        <label class="form-label">AI API Key (VISION_MODEL)</label>
                        <input type="password" class="form-input" id="setApiKey" placeholder="sk-ant-...">
                    </div>

                    <div class="form-group">
                        <label class="form-label">Automatic Sending (ENVIO_AUTOMATICO)</label>
                        <select class="form-select" id="setEnvioAuto">
                            <option value="false">False (Do not send emails to the customer)</option>
                            <option value="true">True (Reply automatically)</option>
                        </select>
                    </div>

                    <div style="display:flex;justify-content:flex-end;margin-top:24px">
                        <button class="btn btn-primary" onclick="Toast.info('Saving settings is under construction.')">Save Changes</button>
                    </div>
                </div>
            </div>
        `;
    }
};
