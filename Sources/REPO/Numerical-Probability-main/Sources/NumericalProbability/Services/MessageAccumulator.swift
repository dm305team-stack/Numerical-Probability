import Foundation

/// Folds SSE events into the final assistant content for one response.
/// Blocks are kept as raw JSONValue so they can be echoed back verbatim on
/// later turns — the API rejects *modified* thinking blocks, and server tool
/// blocks have shapes we deliberately don't model.
struct MessageAccumulator {
    private var blocks: [Int: JSONValue] = [:]
    private var inputBuffers: [Int: String] = [:]

    private(set) var containerID: String?
    private(set) var cacheReadInputTokens: Int?
    private(set) var stopReason: String?
    private(set) var sawMessageStop = false

    mutating func apply(_ event: StreamEvent) {
        switch event {
        case .messageStart(let containerID, let cacheRead):
            self.containerID = containerID
            self.cacheReadInputTokens = cacheRead

        case .blockStart(let index, let block):
            blocks[index] = block

        case .blockDelta(let index, let delta):
            switch delta {
            case .text(let text):
                blocks[index]?.appendString(text, toKey: "text")
            case .thinking(let thinking):
                blocks[index]?.appendString(thinking, toKey: "thinking")
            case .signature(let signature):
                blocks[index]?.setValue(.string(signature), forKey: "signature")
            case .inputJSON(let partial):
                inputBuffers[index, default: ""] += partial
            case .unknownDelta:
                break
            }

        case .blockStop(let index):
            if let buffer = inputBuffers.removeValue(forKey: index), !buffer.isEmpty,
               let input = try? JSONDecoder().decode(JSONValue.self, from: Data(buffer.utf8)) {
                blocks[index]?.setValue(input, forKey: "input")
            }

        case .messageDelta(let stopReason, _):
            if let stopReason {
                self.stopReason = stopReason
            }

        case .messageStop:
            sawMessageStop = true

        case .ping, .streamError, .unknown:
            break
        }
    }

    /// Final assistant content, ordered by stream index, untouched.
    var assistantContent: [JSONValue] {
        blocks.keys.sorted().compactMap { blocks[$0] }
    }

    /// All visible text, in block order.
    var fullText: String {
        assistantContent
            .filter { $0.blockType == "text" }
            .compactMap { $0["text"]?.stringValue }
            .joined()
    }

    /// Thinking summary text, in block order.
    var fullThinking: String {
        assistantContent
            .filter { $0.blockType == "thinking" }
            .compactMap { $0["thinking"]?.stringValue }
            .filter { !$0.isEmpty }
            .joined(separator: "\n\n")
    }

    /// file_ids of files created in the code-execution sandbox, harvested
    /// generically from every server tool result block (exact inner shapes
    /// differ between bash and text_editor results).
    var generatedFileIDs: [String] {
        assistantContent
            .filter { ($0.blockType ?? "").hasSuffix("_tool_result") }
            .flatMap { $0.collectStrings(forKey: "file_id") }
    }
}
