import Foundation

enum RunPhase {
    case idle
    case running(RunProgress)
    case done(RunResult)
    case failed(RunError, partialText: String)

    var isRunning: Bool {
        if case .running = self { return true }
        return false
    }

    var isDone: Bool {
        if case .done = self { return true }
        return false
    }
}

struct RunProgress {
    var completedText: String = ""
    var currentDelta: String = ""
    var thinkingText: String = ""
    var statusLine: String = "Starting…"
    var continuation: Int = 0
}

struct RunResult {
    var reportText: String
    var thinkingText: String
    var sequences: [GeneratedSequence]
    var pdfFileID: String?
    var pdfFilename: String?
    var exportedURL: URL?
    var truncated: Bool = false
}

struct GeneratedSequence: Identifiable {
    let index: Int
    let numbers: [Int]
    let probabilityLabel: String?

    var id: Int { index }

    var display: String {
        let formatted = numbers.map { String(format: "%02d", $0) }
        // 5 + 1 structure: the sixth value is the plus-one number.
        if formatted.count == 6, let plusOne = formatted.last {
            return formatted.dropLast().joined(separator: "  ") + "  +  " + plusOne
        }
        return formatted.joined(separator: "  ")
    }
}

enum ChatPhase {
    case ready
    case streaming(partial: String, statusLine: String)
    case failed(RunError)

    var isStreaming: Bool {
        if case .streaming = self { return true }
        return false
    }
}

enum RunError: Error {
    case missingKey
    case noBasePDF
    case pdfTooLarge(String)
    case http(status: Int, type: String, message: String)
    case network(String)
    case streamError(type: String, message: String)
    case refusal
    case continuationCapExceeded
    case cancelled

    /// Transient errors worth re-POSTing the identical hop for (the request
    /// body is deterministic, so a replay is safe and mostly cache-read).
    var isRetryable: Bool {
        switch self {
        case .http(let status, _, _):
            return status == 429 || status >= 500
        case .streamError(let type, _):
            return type == "overloaded_error" || type == "api_error"
        case .network:
            return true
        default:
            return false
        }
    }

    var userMessage: String {
        switch self {
        case .missingKey:
            return "Add your Anthropic API key in Settings."
        case .noBasePDF:
            return "Import Base-Secuence.pdf before analyzing."
        case .pdfTooLarge(let detail):
            return "PDF too large: \(detail)"
        case .http(let status, let type, let message):
            if status == 401 || status == 403 {
                return "API key rejected (\(type)). Check it in Settings."
            }
            return "Request failed (\(status) \(type)): \(message)"
        case .network(let detail):
            return "Network error: \(detail)"
        case .streamError(let type, let message):
            return "Anthropic is busy (\(type)): \(message). Retry in a moment."
        case .refusal:
            return "The model declined this request."
        case .continuationCapExceeded:
            return "Analysis exceeded the maximum number of continuation rounds."
        case .cancelled:
            return "Stopped."
        }
    }
}

/// Parses the mandated `<final_sequences>` block out of the report text.
/// Line grammar: `1. 04 18 23 35 41 49 | probability: 0.0000072%`
/// Returns [] when the contract was not honored — the run still completes.
enum SequenceParser {
    static func parse(reportText: String) -> [GeneratedSequence] {
        let tagPattern = /<final_sequences>([\s\S]*?)<\/final_sequences>/
        guard let match = reportText.matches(of: tagPattern).last else {
            return []
        }
        let body = String(match.1)

        let linePattern = /^\s*(\d+)[.)]\s+((?:\d{1,2}[\s,]+)*\d{1,2})\s*(?:\|\s*probability:\s*(.+?)\s*)?$/
        var sequences: [GeneratedSequence] = []
        for line in body.split(separator: "\n") {
            guard let lineMatch = line.wholeMatch(of: linePattern) else { continue }
            let index = Int(lineMatch.1) ?? sequences.count + 1
            let numbers = lineMatch.2
                .split(whereSeparator: { $0 == " " || $0 == "," || $0 == "\t" })
                .compactMap { Int($0) }
            guard !numbers.isEmpty else { continue }
            let probability = lineMatch.3.map(String.init)
            sequences.append(
                GeneratedSequence(index: index, numbers: numbers, probabilityLabel: probability))
        }
        return sequences
    }
}
