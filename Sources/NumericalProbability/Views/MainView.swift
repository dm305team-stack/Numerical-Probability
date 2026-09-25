import SwiftUI
import UniformTypeIdentifiers

struct MainView: View {
    @Environment(AppModel.self) private var model
    @State private var showImporter = false
    @State private var chatInput = ""

    var body: some View {
        @Bindable var model = model
        VStack(spacing: 0) {
            header
            Divider()
            content
            Divider()
            chatBar
        }
        .sheet(isPresented: $model.showSettings) {
            VStack(alignment: .trailing) {
                SettingsView()
                Button("Done") { model.showSettings = false }
                    .padding([.trailing, .bottom], 16)
            }
        }
        .fileImporter(
            isPresented: $showImporter,
            allowedContentTypes: [.pdf],
            allowsMultipleSelection: true
        ) { result in
            if case .success(let urls) = result {
                urls.forEach { model.importPDF(at: $0) }
            }
        }
        .dropDestination(for: URL.self) { urls, _ in
            let pdfs = urls.filter { $0.pathExtension.lowercased() == "pdf" }
            pdfs.forEach { model.importPDF(at: $0) }
            return !pdfs.isEmpty
        }
        .onAppear {
            if !model.apiKeyPresent {
                model.showSettings = true
            }
        }
        .onChange(of: model.chatPhase.isStreaming) {
            if let failedText = model.takeFailedChatText(), chatInput.isEmpty {
                chatInput = failedText
            }
        }
    }

    // MARK: - Header

    private var header: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                ForEach(model.knowledge.all) { pdf in
                    knowledgeChip(pdf)
                }
                Button {
                    showImporter = true
                } label: {
                    Label("Import PDF", systemImage: "plus")
                        .font(.callout)
                }
                .buttonStyle(.borderless)
                Spacer()
                Button {
                    model.showSettings = true
                } label: {
                    Image(systemName: "gearshape")
                }
                .buttonStyle(.borderless)
                .help("Settings (API key)")
            }

            HStack(spacing: 12) {
                if model.phase.isRunning {
                    Button(role: .cancel) {
                        model.cancelRun()
                    } label: {
                        Label("Stop", systemImage: "stop.fill")
                    }
                } else {
                    Button {
                        model.analyze()
                    } label: {
                        Label(
                            model.phase.isDone ? "Analyze Again" : "Analyze & Generate",
                            systemImage: "wand.and.stars")
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(!model.canAnalyze)
                    .help(analyzeHint)
                }

                if case .running(let progress) = model.phase {
                    ProgressView().controlSize(.small)
                    Text(progress.statusLine)
                        .font(.callout)
                        .foregroundStyle(.secondary)
                }
                Spacer()
            }

            if let importError = model.importError {
                Label(importError, systemImage: "exclamationmark.triangle.fill")
                    .font(.callout)
                    .foregroundStyle(.orange)
            }
            if !model.apiKeyPresent {
                Label("Add your Anthropic API key to get started", systemImage: "key.fill")
                    .font(.callout)
                    .foregroundStyle(.orange)
            }
        }
        .padding(12)
    }

    private var analyzeHint: String {
        if !model.apiKeyPresent { return "Add your API key in Settings first" }
        if model.knowledge.base == nil { return "Import Base-Secuence.pdf first" }
        return "Run the full 7-step analysis"
    }

    private func knowledgeChip(_ pdf: ImportedPDF) -> some View {
        let isBase = pdf.filename == model.knowledge.base?.filename
        return HStack(spacing: 4) {
            Image(systemName: isBase ? "doc.text.fill" : "doc.text")
                .foregroundStyle(isBase ? AnyShapeStyle(.tint) : AnyShapeStyle(.secondary))
            Text(pdf.filename)
                .font(.callout)
                .lineLimit(1)
                .truncationMode(.middle)
                .frame(maxWidth: 160)
                .fixedSize(horizontal: true, vertical: false)
            Text("\(pdf.pageCount)p")
                .font(.caption2)
                .foregroundStyle(.tertiary)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(.quinary, in: Capsule())
        .help(isBase ? "\(pdf.filename) — pattern source (required)" : "\(pdf.filename) — supporting reference")
    }

    // MARK: - Content

    @ViewBuilder
    private var content: some View {
        switch model.phase {
        case .idle:
            idleView
        case .running(let progress):
            ReportView(progress: progress)
        case .done(let result):
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    if result.truncated {
                        Label("Output hit the token limit — the report may be truncated.",
                              systemImage: "exclamationmark.triangle.fill")
                            .font(.callout)
                            .foregroundStyle(.orange)
                    }
                    ReportBody(
                        completedText: result.reportText,
                        currentDelta: "",
                        thinkingText: result.thinkingText,
                        isFinal: true)
                    SequencesView(result: result)
                    ChatView()
                }
                .padding(16)
            }
        case .failed(let error, let partialText):
            failedView(error: error, partialText: partialText)
        }
    }

    private var idleView: some View {
        VStack(spacing: 14) {
            Spacer()
            Image(systemName: "function")
                .font(.system(size: 44))
                .foregroundStyle(.tertiary)
            Text("Numerical Probability")
                .font(.title2.weight(.semibold))
            Text(model.knowledge.base != nil
                 ? "Knowledge loaded. Run the analysis to detect patterns and generate sequences."
                 : "Import Base-Secuence.pdf (drag & drop works) to begin.")
                .font(.callout)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 420)
            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func failedView(error: RunError, partialText: String) -> some View {
        VStack(spacing: 0) {
            if !partialText.isEmpty {
                ScrollView {
                    VStack(alignment: .leading, spacing: 12) {
                        Text(verbatim: partialText)
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                        Label("Interrupted — partial output above", systemImage: "scissors")
                            .font(.callout)
                            .foregroundStyle(.secondary)
                    }
                    .padding(16)
                }
            } else {
                Spacer()
            }
            HStack(spacing: 12) {
                Label(error.userMessage, systemImage: "exclamationmark.triangle.fill")
                    .foregroundStyle(.orange)
                Spacer()
                Button("Retry") { model.retry() }
                    .buttonStyle(.borderedProminent)
            }
            .padding(12)
            .background(.quinary)
        }
    }

    // MARK: - Chat bar

    private var chatBar: some View {
        VStack(alignment: .leading, spacing: 6) {
            if model.knowledgeIsStale {
                Label("Knowledge changed — chat still answers from the documents used in the last analysis. Run Analyze Again to use the new set.",
                      systemImage: "info.circle.fill")
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 12)
                    .padding(.top, 8)
            }
            chatInputRow
        }
    }

    private var chatInputRow: some View {
        HStack(spacing: 8) {
            TextField(
                model.phase.isDone
                    ? "Ask a follow-up about the analysis…"
                    : "Chat unlocks after the analysis completes",
                text: $chatInput
            )
            .textFieldStyle(.roundedBorder)
            .onSubmit(send)
            .disabled(!model.canChat)

            Button("Send", action: send)
                .disabled(!model.canChat || chatInput.trimmingCharacters(in: .whitespaces).isEmpty)
        }
        .padding(12)
    }

    private func send() {
        let text = chatInput
        chatInput = ""
        model.sendChat(text)
    }
}
