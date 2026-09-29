import SwiftUI
#if canImport(UIKit)
import UIKit
#endif

@main
struct HyvinvointiBridgeApp: App {
    @StateObject private var coordinator = SyncCoordinator()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(coordinator)
        }
    }
}

/// The smallest sensible companion: pair with the code from the web app, choose the data, allow it in Apple's own
/// sheet, synchronize. Everything else (trends, observations, the conversation) happens in the wellbeing agent.
struct ContentView: View {
    @EnvironmentObject private var coordinator: SyncCoordinator

    private var deviceName: String {
        #if canImport(UIKit)
        return UIDevice.current.name
        #else
        return "Mac"
        #endif
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Hyvinvointikumppani") {
                    Text("Hyvinvointikumppani käyttää valitsemiasi terveystietoja henkilökohtaisten hyvinvointitrendien muodostamiseen ja sovittujen seurattavien asioiden seuraamiseen.")
                        .font(.footnote)
                    Text(coordinator.status)
                }
                if !coordinator.isPaired {
                    Section("Yhdistä") {
                        TextField("Palvelimen osoite", text: $coordinator.serverAddress)
                        TextField("Yhdistämiskoodi (Hyvinvointidata-välilehdeltä)", text: $coordinator.pairingCode)
                        Button("Yhdistä") { Task { await coordinator.pair(code: coordinator.pairingCode, deviceName: deviceName) } }
                            .disabled(coordinator.busy || coordinator.pairingCode.filter(\.isNumber).count != 6)
                    }
                }
                Section("Luettavat tiedot") {
                    ForEach(HealthMetric.allCases) { metric in
                        Toggle(metric.title, isOn: Binding(
                            get: { coordinator.selected.contains(metric) },
                            set: { isOn in
                                if isOn { coordinator.selected.insert(metric) } else { coordinator.selected.remove(metric) }
                            }
                        ))
                    }
                    Button("Salli terveystiedot") { Task { await coordinator.authorize() } }
                }
                if coordinator.isPaired {
                    Section("Synkronointi") {
                        if let lastSync = coordinator.lastSync {
                            Text("Viimeisin synkronointi \(lastSync.formatted(date: .numeric, time: .shortened))")
                        }
                        Button("Synkronoi nyt") { Task { await coordinator.syncNow() } }
                            .disabled(coordinator.busy)
                        Button("Poista yhteys tästä laitteesta", role: .destructive) { coordinator.forget() }
                    }
                }
            }
            .navigationTitle("Hyvinvointidata")
        }
    }
}
