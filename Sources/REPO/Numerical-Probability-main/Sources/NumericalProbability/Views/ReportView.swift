import SwiftUI

/// Report content (thinking disclosure + report text). Embedded either in
/// the streaming scroll (anchored bottom) or in the done-phase layout.
struct ReportBody: View {
    let completedText: String
    let currentDelta: String
    let thinkingText: String
    var isFinal: Bool = false

    @State private var showThinking = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if !thinkingText.isEmpty {
                DisclosureGroup(isExpanded: $showThinking) {
                    Text(thinkingText)
                        .font(.callout)
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                } label: {
                    Label("Reasoning", systemImage: "brain")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                }
            }

            reportText
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .textSelection(.enabled)
    }

    @ViewBuilder
    private var reportText: some View {
        if isFinal,
           let attributed = try? AttributedString(
               markdown: completedText,
               options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)) {
            Text(attributed)
        } else {
            // Separate view nodes: SwiftUI's diffing skips re-layout of the
            // (large, stable) completed part; only the small in-flight delta
            // re-lays-out per token. The break lands on a block boundary.
            VStack(alignment: .leading, spacing: 0) {
                Text(verbatim: completedText)
                Text(verbatim: currentDelta)
            }
        }
    }
}

/// Streaming view used while the analysis is running.
struct ReportView: View {
    let progress: RunProgress

    var body: some View {
        ScrollView {
            ReportBody(
                completedText: progress.completedText,
                currentDelta: progress.currentDelta,
                thinkingText: progress.thinkingText
            )
            .padding(16)
        }
        .defaultScrollAnchor(.bottom)
    }
}
