import SwiftUI

struct ChatView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if !model.chatTranscript.isEmpty || model.chatPhase.isStreaming {
                Divider()
                Label("Follow-up", systemImage: "bubble.left.and.bubble.right")
                    .font(.headline)

                ForEach(model.chatTranscript) { entry in
                    bubble(role: entry.role, text: entry.text)
                }

                if case .streaming(let partial, let status) = model.chatPhase {
                    if partial.isEmpty {
                        HStack(spacing: 8) {
                            ProgressView().controlSize(.small)
                            Text(status)
                                .font(.callout)
                                .foregroundStyle(.secondary)
                        }
                    } else {
                        bubble(role: "assistant", text: partial)
                    }
                }

                if case .failed(let error) = model.chatPhase {
                    Label(error.userMessage, systemImage: "exclamationmark.triangle.fill")
                        .font(.callout)
                        .foregroundStyle(.orange)
                }
            }
        }
    }

    @ViewBuilder
    private func bubble(role: String, text: String) -> some View {
        let isUser = role == "user"
        HStack {
            if isUser { Spacer(minLength: 60) }
            Text(text)
                .textSelection(.enabled)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(
                    isUser ? AnyShapeStyle(.tint.opacity(0.18)) : AnyShapeStyle(.quinary),
                    in: RoundedRectangle(cornerRadius: 10))
                .frame(maxWidth: .infinity, alignment: isUser ? .trailing : .leading)
            if !isUser { Spacer(minLength: 60) }
        }
    }
}
