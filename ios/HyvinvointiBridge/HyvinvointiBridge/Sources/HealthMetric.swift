import Foundation
import HealthKit

/// The metrics of the first version. Read access only; the ids match the backend's catalog
/// (data/support/policies.json → wellbeingData.metrics) and the JSON keys of /api/health/sync.
enum HealthMetric: String, CaseIterable, Identifiable {
    case steps
    case sleepMinutes
    case restingHeartRate
    case hrvMs
    case activeEnergyKcal
    case workoutMinutes
    case weightKg
    case vo2Max

    var id: String { rawValue }

    var title: String {
        switch self {
        case .steps: return "Askeleet"
        case .sleepMinutes: return "Uni"
        case .restingHeartRate: return "Leposyke"
        case .hrvMs: return "HRV"
        case .activeEnergyKcal: return "Aktiivinen energia"
        case .workoutMinutes: return "Liikuntasuoritukset"
        case .weightKg: return "Paino"
        case .vo2Max: return "VO2 max"
        }
    }

    /// The HealthKit type that is read (never written).
    var objectType: HKObjectType {
        switch self {
        case .steps: return HKQuantityType(.stepCount)
        case .sleepMinutes: return HKCategoryType(.sleepAnalysis)
        case .restingHeartRate: return HKQuantityType(.restingHeartRate)
        case .hrvMs: return HKQuantityType(.heartRateVariabilitySDNN)
        case .activeEnergyKcal: return HKQuantityType(.activeEnergyBurned)
        case .workoutMinutes: return HKObjectType.workoutType()
        case .weightKg: return HKQuantityType(.bodyMass)
        case .vo2Max: return HKQuantityType(.vo2Max)
        }
    }
}

/// One day's summary as the backend expects it. Only summaries leave the phone - never individual samples.
struct DailyMetrics: Codable, Equatable {
    var date: String
    var steps: Int?
    var sleepMinutes: Int?
    var restingHeartRate: Double?
    var hrvMs: Double?
    var activeEnergyKcal: Int?
    var workoutMinutes: Int?
    var workoutCount: Int?
    var weightKg: Double?
    var vo2Max: Double?

    var isEmpty: Bool {
        steps == nil && sleepMinutes == nil && restingHeartRate == nil && hrvMs == nil && activeEnergyKcal == nil
            && workoutMinutes == nil && weightKg == nil && vo2Max == nil
    }
}

struct SyncPayload: Encodable {
    let source = "apple_health"
    let deviceId: String?
    let dailyMetrics: [DailyMetrics]
}

struct SyncResponse: Decodable {
    let created: Int
    let updated: Int
    let lastSyncAt: String?
}

struct PairResponse: Decodable {
    let deviceId: String
    let deviceToken: String
}
