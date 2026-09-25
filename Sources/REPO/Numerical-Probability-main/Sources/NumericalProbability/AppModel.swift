import Foundation
import PDFKit
import SwiftUI

struct ImportedPDF: Identifiable {
    let filename: String
    let data: Data
    let base64: String
    let pageCount: Int

    var id: String { filename }
}

struct KnowledgeSet {
    var base: ImportedPDF?
    var supporting: [ImportedPDF] = []

    /// Documents in request order: base first, then supporting by name.
    var all: [ImportedPDF] {
        (base.map { [$0] } ?? []) + supporting.sorted { $0.filename < $1.filename }
    }
}

struct ChatEntry: Identifiable {
    let id = UUID()
    let role: String  // "user" | "assistant"
    let text: String
}

@MainActor
@Observable
final class AppModel {
    var apiKeyPresent = false
    var knowledge = KnowledgeSet()
    var phase: RunPhase = .idle
    var chatPhase: ChatPhase = .ready
    var chatTranscript: [ChatEntry] = []
    var exportError: String?
    var importError: String?
    var showSettings = false

    /// Canonical replay history — only complete, successful turns enter.
    /// User text blocks are stored WITHOUT cache_control; the moving
    /// breakpoint is added at request-build time to the newest user turn.
    private(set) var messages: [ApiMessage] = []
    private(set) var containerID: String?

    private let client = AnthropicClient()
    private let downloader = FileDownloader()
    private var runTask: Task<Void, Never>?
    private var pendingChatText: String?

    private static let maxContinuations = 8
    private static let maxAttempts = 3
    private static let reportFilename = "Numerical_Probability_Report.pdf"

    /// Snapshot of the knowledge set the current conversation was built on.
    private var analyzedKnowledgeIDs: [String] = []

    private static func knowledgeIDs(_ documents: [ImportedPDF]) -> [String] {
        documents.map { "\($0.filename)|\($0.data.count)" }
    }

    /// True when documents were imported/replaced after the analysis ran —
    /// chat keeps answering from the old embedded set until re-analyzed.
    var knowledgeIsStale: Bool {
        phase.isDone && Self.knowledgeIDs(knowledge.all) != analyzedKnowledgeIDs
    }

    init() {
        refreshKey()
        loadKnowledgeFromFolder()
    }

    // MARK: - API key

    func refreshKey() {
        apiKeyPresent = KeychainStore.loadKey() != nil
    }

    // MARK: - Knowledge import

    /// Project root candidates: cwd (swift run) and two levels above the
    /// bundle (dist/NumericalProbability.app inside the project).
    private var knowledgeFolderCandidates: [URL] {
        var roots = [URL(fileURLWithPath: FileManager.default.currentDirectoryPath)]
        let bundleParent = Bundle.main.bundleURL
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        roots.append(bundleParent)
        return roots.map { $0.appendingPathComponent("Knowledge", isDirectory: true) }
    }

    func loadKnowledgeFromFolder() {
        for folder in knowledgeFolderCandidates {
            guard let entries = try? FileManager.default.contentsOfDirectory(
                at: folder, includingPropertiesForKeys: nil)
            else { continue }
            let pdfs = entries.filter { $0.pathExtension.lowercased() == "pdf" }
            guard !pdfs.isEmpty else { continue }
            for url in pdfs.sorted(by: { $0.lastPathComponent < $1.lastPathComponent }) {
                importPDF(at: url)
            }
            return
        }
    }

    func importPDF(at url: URL) {
        guard let data = try? Data(contentsOf: url) else {
            importError = "Could not read \(url.lastPathComponent)"
            return
        }
        let pageCount = PDFDocument(data: data)?.pageCount ?? 0
        guard pageCount > 0 else {
            importError = "\(url.lastPathComponent) is not a readable PDF"
            return
        }
        guard pageCount <= 100 else {
            importError = "\(url.lastPathComponent) has \(pageCount) pages — the API limit is 100 per document"
            return
        }
        let pdf = ImportedPDF(
            filename: url.lastPathComponent,
            data: data,
            base64: data.base64EncodedString(),
            pageCount: pageCount
        )
        let isBase = url.lastPathComponent.lowercased().hasPrefix("base")
        if isBase {
            knowledge.base = pdf
        } else {
            knowledge.supporting.removeAll { $0.filename == pdf.filename }
            knowledge.supporting.append(pdf)
        }

        let totalBytes = knowledge.all.map(\.base64.utf8.count).reduce(0, +)
        if totalBytes > 25_000_000 {
            importError = "Knowledge set is close to the 32 MB request limit — remove a document"
        }
    }

    var canAnalyze: Bool {
        apiKeyPresent && knowledge.base != nil && !phase.isRunning && !chatPhase.isStreaming
    }

    // MARK: - Analysis run

    func analyze() {
        // Never start while another stream is consuming runTask — two
        // concurrent turn loops would corrupt the conversation history.
        guard !phase.isRunning, !chatPhase.isStreaming else { return }
        guard let apiKey = KeychainStore.loadKey() else {
            phase = .failed(.missingKey, partialText: "")
            return
        }
        guard knowledge.base != nil else {
            phase = .failed(.noBasePDF, partialText: "")
            return
        }

        // Fresh conversation: the analysis turn is always turn one.
        messages = []
        containerID = nil
        chatTranscript = []
        chatPhase = .ready
        phase = .running(RunProgress())

        let documents = knowledge.all
        analyzedKnowledgeIDs = Self.knowledgeIDs(documents)
        runTask = Task { [weak self] in
            await self?.runAnalysis(apiKey: apiKey, documents: documents)
        }
    }

    private func kickoffContent(documents: [ImportedPDF]) -> [JSONValue] {
        var content: [JSONValue] = []
        for (i, pdf) in documents.enumerated() {
            content.append(MessageBuilder.documentBlock(
                base64: pdf.base64,
                title: pdf.filename,
                // Single fixed 1-h breakpoint on the LAST document caches
                // tools + system + all PDFs as one prefix.
                oneHourCache: i == documents.count - 1
            ))
        }
        content.append(MessageBuilder.textBlock(Prompts.kickoff))
        return content
    }

    private func runAnalysis(apiKey: String, documents: [ImportedPDF]) async {
        do {
            let userMessage = ApiMessage(role: "user", content: kickoffContent(documents: documents))
            let outcome = try await performTurn(
                history: [],
                newUserMessage: userMessage,
                apiKey: apiKey
            ) { [weak self] progress in
                self?.phase = .running(progress)
            }

            let sequences = SequenceParser.parse(reportText: outcome.text)
            let pdf = await resolveReportPDF(fileIDs: outcome.fileIDs, apiKey: apiKey)

            messages = outcome.newMessages
            phase = .done(RunResult(
                reportText: outcome.text,
                thinkingText: outcome.thinking,
                sequences: sequences,
                pdfFileID: pdf?.id,
                pdfFilename: pdf?.filename,
                exportedURL: nil,
                truncated: outcome.maxTokensHit
            ))
        } catch is CancellationError {
            let partial: String
            if case .running(let progress) = phase {
                partial = progress.completedText + progress.currentDelta
            } else {
                partial = ""
            }
            phase = .failed(.cancelled, partialText: partial)
        } catch let error as RunError {
            let partial: String
            if case .refusal = error {
                partial = ""  // never display or trust refused partial output
            } else if case .running(let progress) = phase {
                partial = progress.completedText + progress.currentDelta
            } else {
                partial = ""
            }
            phase = .failed(error, partialText: partial)
        } catch {
            phase = .failed(.network(error.localizedDescription), partialText: "")
        }
    }

    func cancelRun() {
        runTask?.cancel()
    }

    func retry() {
        if case .failed = phase {
            analyze()
        }
    }

    // MARK: - Shared turn loop (analysis + chat), with pause_turn auto-resume

    private struct TurnOutcome {
        var newMessages: [ApiMessage]
        var text: String
        var thinking: String
        var fileIDs: [String]
        var maxTokensHit: Bool
    }

    private func performTurn(
        history: [ApiMessage],
        newUserMessage: ApiMessage,
        apiKey: String,
        onProgress: @escaping (RunProgress) -> Void
    ) async throws -> TurnOutcome {
        var working = history + [newUserMessage]
        var progress = RunProgress()
        var allText = ""
        var allThinking = ""
        var fileIDs: [String] = []
        var maxTokensHit = false
        var hop = 0

        var attempt = 0
        turnLoop: while true {
            let body = RequestBuilder.messagesBody(
                systemPrompt: Prompts.system,
                messages: Self.withRequestCacheBreakpoints(working),
                container: containerID
            )

            var accumulator = MessageAccumulator()
            var currentBlockType: String?
            let progressSnapshot = progress

            do {
                for try await event in client.stream(body: body, apiKey: apiKey) {
                    accumulator.apply(event)

                    switch event {
                    case .blockStart(_, let block):
                        currentBlockType = block.blockType
                        progress.statusLine = Self.status(
                            blockType: block.blockType,
                            toolName: block["name"]?.stringValue,
                            hop: hop)
                    case .blockDelta(_, let delta):
                        switch delta {
                        case .text(let text):
                            progress.currentDelta += text
                        case .thinking(let thinking):
                            progress.thinkingText += thinking
                        default:
                            break
                        }
                    case .blockStop:
                        if currentBlockType == "text" {
                            progress.completedText += progress.currentDelta
                            progress.currentDelta = ""
                        }
                        currentBlockType = nil
                    default:
                        break
                    }
                    onProgress(progress)
                }

                // A cancelled consumer exits the loop CLEANLY (next() returns
                // nil, nothing throws) — never let a half-received message
                // pass as a completed turn.
                try Task.checkCancellation()
                guard accumulator.sawMessageStop else {
                    throw RunError.network("Stream ended before message_stop")
                }
            } catch let error as RunError where error.isRetryable && attempt + 1 < Self.maxAttempts {
                // The hop body is deterministic (sortedKeys, frozen prompts),
                // so re-POSTing it is safe and mostly a cache read.
                attempt += 1
                progress = progressSnapshot
                progress.statusLine = "Connection hiccup — retrying (attempt \(attempt + 1))…"
                onProgress(progress)
                try await Task.sleep(for: .seconds(attempt * 4))
                continue turnLoop
            }
            attempt = 0

            if let cid = accumulator.containerID {
                containerID = cid
            }
            #if DEBUG
            if let cacheRead = accumulator.cacheReadInputTokens {
                print("[cache] read \(cacheRead) input tokens from cache (hop \(hop))")
            }
            #endif

            // pause_turn resumes must keep exactly ONE trailing assistant
            // message — consecutive assistant messages are a 400 ("roles
            // must alternate"), and would poison the committed history.
            if working.last?.role == "assistant" {
                working[working.count - 1].content += accumulator.assistantContent
            } else {
                working.append(ApiMessage(role: "assistant", content: accumulator.assistantContent))
            }
            allText += accumulator.fullText
            allThinking += allThinking.isEmpty || accumulator.fullThinking.isEmpty ? accumulator.fullThinking : "\n\n" + accumulator.fullThinking
            fileIDs.append(contentsOf: accumulator.generatedFileIDs)

            switch accumulator.stopReason {
            case "pause_turn":
                hop += 1
                guard hop <= Self.maxContinuations else {
                    throw RunError.continuationCapExceeded
                }
                progress.statusLine = "Resuming analysis (round \(hop + 1))…"
                onProgress(progress)
                continue turnLoop
            case "refusal":
                throw RunError.refusal
            case "max_tokens":
                maxTokensHit = true
                break turnLoop
            default:  // end_turn, stop_sequence, nil
                break turnLoop
            }
        }

        return TurnOutcome(
            newMessages: working,
            text: allText,
            thinking: allThinking,
            fileIDs: fileIDs,
            maxTokensHit: maxTokensHit
        )
    }

    /// Request-build-time cache breakpoints (the stored history carries only
    /// the fixed 1-h marker on the last document block):
    /// - moving ephemeral marker on the newest user turn's last text block;
    /// - ephemeral marker on the newest assistant message's last eligible
    ///   block, so pause_turn hops and post-analysis chat turns re-read the
    ///   accumulated transcript from cache instead of re-billing it;
    /// - one mid-message marker when that assistant message is long, keeping
    ///   consecutive entries within the API's 20-block cache lookback.
    /// Budget: at most 4 markers per request — exactly the API maximum.
    private static func withRequestCacheBreakpoints(_ messages: [ApiMessage]) -> [ApiMessage] {
        var result = messages
        let ephemeral = JSONValue.object(["type": .string("ephemeral")])

        if let lastUserIndex = result.lastIndex(where: { $0.role == "user" }),
           let lastTextIndex = result[lastUserIndex].content.lastIndex(where: { $0.blockType == "text" }) {
            result[lastUserIndex].content[lastTextIndex].setValue(ephemeral, forKey: "cache_control")
        }

        // Thinking blocks can't carry cache_control, and server tool RESULT
        // blocks aren't documented as eligible — text and server_tool_use
        // are the safe carriers.
        let eligible: (JSONValue) -> Bool = { block in
            block.blockType == "text" || block.blockType == "server_tool_use"
        }
        if let lastAssistantIndex = result.lastIndex(where: { $0.role == "assistant" }) {
            var content = result[lastAssistantIndex].content
            if let tail = content.indices.last(where: { eligible(content[$0]) }) {
                content[tail].setValue(ephemeral, forKey: "cache_control")
                let midTarget = tail - 12
                if tail >= 16,
                   let mid = content.indices.first(where: { $0 >= midTarget && $0 < tail && eligible(content[$0]) }) {
                    content[mid].setValue(ephemeral, forKey: "cache_control")
                }
                result[lastAssistantIndex].content = content
            }
        }
        return result
    }

    private static func status(blockType: String?, toolName: String?, hop: Int) -> String {
        var status: String
        switch blockType {
        case "thinking":
            status = "Thinking…"
        case "server_tool_use":
            status = toolName == "text_editor_code_execution" ? "Writing files…" : "Running Python…"
        case "text":
            status = "Writing report…"
        default:
            status = "Working…"
        }
        if hop > 0 {
            status += " (round \(hop + 1))"
        }
        return status
    }

    // MARK: - Report PDF resolution

    private func resolveReportPDF(fileIDs: [String], apiKey: String) async -> (id: String, filename: String)? {
        // Keep the LAST match in both branches: the model may write the
        // report, inspect it, and rewrite the same path — newest wins.
        var exact: (id: String, filename: String)?
        var fallback: (id: String, filename: String)?
        var seen = Set<String>()
        for fileID in fileIDs where seen.insert(fileID).inserted {
            guard let meta = try? await downloader.metadata(fileID: fileID, apiKey: apiKey) else {
                continue
            }
            if meta.filename == Self.reportFilename {
                exact = (fileID, meta.filename)
            } else if meta.filename.lowercased().hasSuffix(".pdf") {
                fallback = (fileID, meta.filename)
            }
        }
        return exact ?? fallback
    }

    // MARK: - Chat

    var canChat: Bool {
        phase.isDone && !chatPhase.isStreaming && apiKeyPresent
    }

    func sendChat(_ text: String) {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard canChat, !trimmed.isEmpty, let apiKey = KeychainStore.loadKey() else { return }

        pendingChatText = trimmed
        chatTranscript.append(ChatEntry(role: "user", text: trimmed))
        chatPhase = .streaming(partial: "", statusLine: "Sending…")

        runTask = Task { [weak self] in
            await self?.runChatTurn(text: trimmed, apiKey: apiKey)
        }
    }

    private func runChatTurn(text: String, apiKey: String) async {
        do {
            let userMessage = ApiMessage(role: "user", content: [MessageBuilder.textBlock(text)])
            let outcome = try await performTurn(
                history: messages,
                newUserMessage: userMessage,
                apiKey: apiKey
            ) { [weak self] progress in
                self?.chatPhase = .streaming(
                    partial: progress.completedText + progress.currentDelta,
                    statusLine: progress.statusLine)
            }

            messages = outcome.newMessages
            let note = outcome.maxTokensHit ? "\n\n⚠️ Output hit the token limit — answer may be truncated." : ""
            chatTranscript.append(ChatEntry(role: "assistant", text: outcome.text + note))
            pendingChatText = nil
            chatPhase = .ready

            // A follow-up may regenerate the report PDF and/or emit a fresh
            // <final_sequences> block — keep the card and export in sync.
            if case .done(var result) = phase {
                let newSequences = SequenceParser.parse(reportText: outcome.text)
                if !newSequences.isEmpty {
                    result.sequences = newSequences
                }
                if !outcome.fileIDs.isEmpty,
                   let pdf = await resolveReportPDF(fileIDs: outcome.fileIDs, apiKey: apiKey) {
                    result.pdfFileID = pdf.id
                    result.pdfFilename = pdf.filename
                    result.exportedURL = nil
                }
                phase = .done(result)
            }
        } catch is CancellationError {
            if chatTranscript.last?.role == "user" {
                chatTranscript.removeLast()
            }
            chatPhase = .failed(.cancelled)
        } catch let error as RunError {
            // Drop the unanswered user bubble; the text returns to the input.
            if chatTranscript.last?.role == "user" {
                chatTranscript.removeLast()
            }
            chatPhase = .failed(error)
        } catch {
            if chatTranscript.last?.role == "user" {
                chatTranscript.removeLast()
            }
            chatPhase = .failed(.network(error.localizedDescription))
        }
    }

    /// Text restored to the input box after a failed chat turn.
    func takeFailedChatText() -> String? {
        guard case .failed = chatPhase else { return nil }
        defer { pendingChatText = nil }
        return pendingChatText
    }

    // MARK: - Export

    func exportPDF() {
        guard case .done(let result) = phase,
              let fileID = result.pdfFileID,
              let apiKey = KeychainStore.loadKey()
        else { return }
        let suggestedFilename = result.pdfFilename ?? Self.reportFilename

        exportError = nil
        Task {
            do {
                let data = try await downloader.download(fileID: fileID, apiKey: apiKey)
                let url = PDFExporter.save(data: data, suggestedFilename: suggestedFilename)
                // The save panel can sit open for minutes — re-validate the
                // phase before writing back, instead of restoring a stale copy.
                if let url, case .done(var current) = phase, current.pdfFileID == fileID {
                    current.exportedURL = url
                    phase = .done(current)
                }
            } catch let error as RunError {
                exportError = error.userMessage
            } catch {
                exportError = error.localizedDescription
            }
        }
    }
}
