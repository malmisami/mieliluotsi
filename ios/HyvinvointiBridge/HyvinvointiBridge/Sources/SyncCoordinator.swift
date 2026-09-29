import Foundation

/// Incremental synchronization: the first sync sends a year of history, later ones only the days since the last
/// sync plus two earlier days (HealthKit data arrives late, e.g. the night's sleep or a watch that was not synced).
/// The backend upserts by source and date, so re-sending a day never creates a duplicate.
@MainActor
final class SyncCoordinator: ObservableObject {
    @Published var status = "Ei yhdistetty"
    @Published var lastSync: Date? = UserDefaults.standard.object(forKey: "lastSync") as? Date
    @Published var isPaired = TokenStore.load() != nil
    @Published var busy = false
    @Published var selected: Set<HealthMetric> = Set(HealthMetric.allCases)
    @Published var serverAddress = UserDefaults.standard.string(forKey: "serverAddress") ?? "http://localhost:8002"
    @Published var pairingCode = ""

    private let reader = HealthKitReader()
    private let historyDays = 365
    private let overlapDays = 2
    private let chunkDays = 120  // the backend accepts at most 400 days per request

    private var client: BackendClient? {
        URL(string: serverAddress).map { BackendClient(baseURL: $0) }
    }

    func pair(code: String, deviceName: String) async {
        guard let client else { status = "Palvelimen osoite ei kelpaa."; return }
        busy = true
        defer { busy = false }
        do {
            UserDefaults.standard.set(serverAddress, forKey: "serverAddress")
            let response = try await client.pair(code: code.filter(\.isNumber), deviceName: deviceName)
            TokenStore.save(response.deviceToken)
            UserDefaults.standard.set(response.deviceId, forKey: "deviceId")
            isPaired = true
            pairingCode = ""
            status = "Yhdistetty. Salli seuraavaksi luettavat terveystiedot."
        } catch {
            status = error.localizedDescription
        }
    }

    func authorize() async {
        guard reader.isAvailable else { status = "Terveystiedot eivät ole käytettävissä tällä laitteella."; return }
        do {
            try await reader.requestAuthorization(for: Array(selected))
            status = "Luvat pyydetty. Voit synkronoida."
        } catch {
            status = error.localizedDescription
        }
    }

    func syncNow() async {
        guard let client, let token = TokenStore.load() else { status = "Yhdistä ensin koodilla."; return }
        busy = true
        defer { busy = false }
        let calendar = Calendar.current
        let end = calendar.date(byAdding: .day, value: 1, to: calendar.startOfDay(for: Date())) ?? Date()
        let firstDay = calendar.date(byAdding: .day, value: -historyDays, to: end) ?? end
        let start = lastSync.flatMap { calendar.date(byAdding: .day, value: -overlapDays, to: calendar.startOfDay(for: $0)) }
            .map { max($0, firstDay) } ?? firstDay
        do {
            let days = try await reader.dailyMetrics(for: selected, from: start, to: end)
            var sent = 0
            for offset in stride(from: 0, to: days.count, by: chunkDays) {
                let chunk = Array(days[offset..<min(offset + chunkDays, days.count)])
                _ = try await client.sync(days: chunk, deviceId: UserDefaults.standard.string(forKey: "deviceId"), token: token)
                sent += chunk.count
            }
            lastSync = Date()
            UserDefaults.standard.set(lastSync, forKey: "lastSync")
            status = "Synkronoitu \(sent) päivän yhteenvedot."
        } catch {
            status = error.localizedDescription
        }
    }

    func forget() {
        TokenStore.delete()
        UserDefaults.standard.removeObject(forKey: "lastSync")
        UserDefaults.standard.removeObject(forKey: "deviceId")
        isPaired = false
        lastSync = nil
        status = "Yhteys poistettu tästä laitteesta. Katkaise yhteys myös Hyvinvointidata-välilehdellä."
    }
}
