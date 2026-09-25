import SwiftUI

struct SettingsView: View {
    @Environment(AppModel.self) private var model
    @State private var keyInput = ""
    @State private var saved = false

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Anthropic API Key")
                .font(.headline)

            Text("Stored in the macOS Keychain. Get one at console.anthropic.com.")
                .font(.callout)
                .foregroundStyle(.secondary)

            HStack {
                SecureField("sk-ant-…", text: $keyInput)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit(save)
                Button("Save", action: save)
                    .keyboardShortcut(.defaultAction)
                    .disabled(keyInput.trimmingCharacters(in: .whitespaces).isEmpty)
            }

            HStack(spacing: 8) {
                Image(systemName: model.apiKeyPresent ? "checkmark.circle.fill" : "exclamationmark.circle.fill")
                    .foregroundStyle(model.apiKeyPresent ? .green : .orange)
                Text(model.apiKeyPresent ? "API key present" : "No API key configured")
                    .font(.callout)
                Spacer()
                if model.apiKeyPresent {
                    Button("Delete Key", role: .destructive) {
                        KeychainStore.deleteKey()
                        model.refreshKey()
                        saved = false
                    }
                }
            }

            if saved {
                Text("Saved.")
                    .font(.callout)
                    .foregroundStyle(.green)
            }
        }
        .padding(20)
        .frame(width: 420)
    }

    private func save() {
        let key = keyInput.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !key.isEmpty else { return }
        saved = KeychainStore.save(key)
        keyInput = ""
        model.refreshKey()
    }
}
