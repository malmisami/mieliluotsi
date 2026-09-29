import Foundation

/// The secure API between the bridge and the backend: pairing with the one-time code shown in the web app, then
/// daily summaries with the device's own token. The person is decided by the token on the server - the app never
/// sends a user id.
struct BackendClient {
    enum ClientError: LocalizedError {
        case server(Int, String)

        var errorDescription: String? {
            switch self {
            case let .server(status, detail): return "Palvelin vastasi \(status): \(detail)"
            }
        }
    }

    var baseURL: URL
    var session: URLSession = .shared

    func pair(code: String, deviceName: String) async throws -> PairResponse {
        let body = try JSONSerialization.data(withJSONObject: ["code": code, "deviceName": deviceName])
        return try await send(path: "/api/health/devices/pair", body: body, token: nil)
    }

    func sync(days: [DailyMetrics], deviceId: String?, token: String) async throws -> SyncResponse {
        let body = try JSONEncoder().encode(SyncPayload(deviceId: deviceId, dailyMetrics: days))
        return try await send(path: "/api/health/sync", body: body, token: token)
    }

    private func send<T: Decodable>(path: String, body: Data, token: String?) async throws -> T {
        var request = URLRequest(url: baseURL.appendingPathComponent(path))
        request.httpMethod = "POST"
        request.httpBody = body
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let token {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        let (data, response) = try await session.data(for: request)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(status) else {
            let detail = (try? JSONSerialization.jsonObject(with: data) as? [String: Any])?["detail"] as? String ?? "virhe"
            throw ClientError.server(status, detail)
        }
        return try JSONDecoder().decode(T.self, from: data)
    }
}
