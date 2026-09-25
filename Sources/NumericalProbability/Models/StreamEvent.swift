import Foundation

/// Typed view over the SSE events of a streaming /v1/messages response.
/// Unknown event and delta types map to .unknown / .unknownDelta and are
/// ignored downstream (forward compatibility per API versioning policy).
enum StreamEvent: Sendable {
    case messageStart(containerID: String?, cacheReadInputTokens: Int?)
    case blockStart(index: Int, block: JSONValue)
    case blockDelta(index: Int, delta: BlockDelta)
    case blockStop(index: Int)
    case messageDelta(stopReason: String?, outputTokens: Int?)
    case messageStop
    case ping
    case streamError(type: String, message: String)
    case unknown

    enum BlockDelta: Sendable {
        case text(String)
        case thinking(String)
        case signature(String)
        case inputJSON(String)
        case unknownDelta
    }

    /// Maps one decoded `data:` payload to an event. Dispatches on the JSON
    /// "type" field (it duplicates the SSE event name).
    init(json: JSONValue) {
        switch json.blockType {
        case "message_start":
            let message = json["message"]
            self = .messageStart(
                containerID: message?["container"]?["id"]?.stringValue,
                cacheReadInputTokens: message?["usage"]?["cache_read_input_tokens"]?.intValue
            )
        case "content_block_start":
            guard let index = json["index"]?.intValue, let block = json["content_block"] else {
                self = .unknown
                return
            }
            self = .blockStart(index: index, block: block)
        case "content_block_delta":
            guard let index = json["index"]?.intValue, let delta = json["delta"] else {
                self = .unknown
                return
            }
            let blockDelta: BlockDelta
            switch delta.blockType {
            case "text_delta":
                blockDelta = .text(delta["text"]?.stringValue ?? "")
            case "thinking_delta":
                blockDelta = .thinking(delta["thinking"]?.stringValue ?? "")
            case "signature_delta":
                blockDelta = .signature(delta["signature"]?.stringValue ?? "")
            case "input_json_delta":
                blockDelta = .inputJSON(delta["partial_json"]?.stringValue ?? "")
            default:
                blockDelta = .unknownDelta
            }
            self = .blockDelta(index: index, delta: blockDelta)
        case "content_block_stop":
            guard let index = json["index"]?.intValue else {
                self = .unknown
                return
            }
            self = .blockStop(index: index)
        case "message_delta":
            self = .messageDelta(
                stopReason: json["delta"]?["stop_reason"]?.stringValue,
                outputTokens: json["usage"]?["output_tokens"]?.intValue
            )
        case "message_stop":
            self = .messageStop
        case "ping":
            self = .ping
        case "error":
            self = .streamError(
                type: json["error"]?["type"]?.stringValue ?? "unknown_error",
                message: json["error"]?["message"]?.stringValue ?? "Unknown stream error"
            )
        default:
            self = .unknown
        }
    }
}
