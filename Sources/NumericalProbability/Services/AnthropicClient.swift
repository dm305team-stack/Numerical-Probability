import Foundation

/// Raw URLSession client for the Anthropic Messages API (streaming SSE).
/// No SDK exists for Swift; raw HTTP is the sanctioned integration path.
struct AnthropicClient: Sendable {
    static let baseURL = URL(string: "https://api.anthropic.com")!
    static let apiVersion = "2023-06-01"

    private let session: URLSession

    init() {
        let configuration = URLSessionConfiguration.ephemeral
        // timeoutIntervalForRequest is an *idle* timer — code-execution
        // phases can go quiet for minutes between bytes.
        configuration.timeoutIntervalForRequest = 600
        configuration.timeoutIntervalForResource = 3600
        session = URLSession(configuration: configuration)
    }

    /// Streams one /v1/messages request. The stream finishes after
    /// message_stop, or throws RunError on HTTP/network/stream errors.
    func stream(body: JSONValue, apiKey: String) -> AsyncThrowingStream<StreamEvent, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    var request = URLRequest(url: Self.baseURL.appendingPathComponent("v1/messages"))
                    request.httpMethod = "POST"
                    request.setValue(apiKey, forHTTPHeaderField: "x-api-key")
                    request.setValue(Self.apiVersion, forHTTPHeaderField: "anthropic-version")
                    request.setValue("application/json", forHTTPHeaderField: "content-type")
                    request.httpBody = try RequestBuilder.encode(body)

                    let (bytes, response) = try await session.bytes(for: request)
                    guard let http = response as? HTTPURLResponse else {
                        throw RunError.network("No HTTP response")
                    }

                    if http.statusCode != 200 {
                        var errorBody = Data()
                        for try await byte in bytes {
                            errorBody.append(byte)
                        }
                        throw Self.decodeHTTPError(status: http.statusCode, body: errorBody)
                    }

                    let decoder = JSONDecoder()
                    for try await line in bytes.lines {
                        try Task.checkCancellation()
                        guard line.hasPrefix("data:") else { continue }
                        let payload = line.dropFirst(5).trimmingCharacters(in: .whitespaces)
                        guard !payload.isEmpty,
                              let json = try? decoder.decode(JSONValue.self, from: Data(payload.utf8))
                        else { continue }

                        let event = StreamEvent(json: json)
                        if case .streamError(let type, let message) = event {
                            throw RunError.streamError(type: type, message: message)
                        }
                        continuation.yield(event)
                        if case .messageStop = event {
                            break
                        }
                    }
                    continuation.finish()
                } catch is CancellationError {
                    continuation.finish(throwing: RunError.cancelled)
                } catch let error as RunError {
                    continuation.finish(throwing: error)
                } catch let error as URLError where error.code == .cancelled {
                    continuation.finish(throwing: RunError.cancelled)
                } catch {
                    continuation.finish(throwing: RunError.network(error.localizedDescription))
                }
            }
            continuation.onTermination = { _ in
                task.cancel()
            }
        }
    }

    private static func decodeHTTPError(status: Int, body: Data) -> RunError {
        if let json = try? JSONDecoder().decode(JSONValue.self, from: body),
           let type = json["error"]?["type"]?.stringValue {
            let message = json["error"]?["message"]?.stringValue ?? ""
            return .http(status: status, type: type, message: message)
        }
        return .http(
            status: status,
            type: "unknown_error",
            message: String(data: body.prefix(500), encoding: .utf8) ?? "")
    }
}
