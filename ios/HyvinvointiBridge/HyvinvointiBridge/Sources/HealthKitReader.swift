import Foundation
import HealthKit

/// Reads HealthKit and turns it into daily summaries: sums (steps, energy, sleep, workouts), daily averages (resting
/// heart rate, HRV) and the latest value of the day (weight, VO2 max). Read permission only.
final class HealthKitReader {
    private let store = HKHealthStore()
    private let calendar = Calendar.current
    private let dayFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter
    }()

    var isAvailable: Bool { HKHealthStore.isHealthDataAvailable() }

    /// Apple shows its own sheet where the user allows each type separately. Nothing is written (toShare is empty).
    func requestAuthorization(for metrics: [HealthMetric]) async throws {
        try await store.requestAuthorization(toShare: [], read: Set(metrics.map(\.objectType)))
    }

    /// Daily summaries for the days in [start, end). Days without any data are left out.
    func dailyMetrics(for metrics: Set<HealthMetric>, from start: Date, to end: Date) async throws -> [DailyMetrics] {
        var days: [String: DailyMetrics] = [:]
        func update(_ values: [Date: Double], _ apply: (inout DailyMetrics, Double) -> Void) {
            for (date, value) in values {
                let key = dayFormatter.string(from: date)
                var day = days[key] ?? DailyMetrics(date: key)
                apply(&day, value)
                days[key] = day
            }
        }
        let beatsPerMinute = HKUnit.count().unitDivided(by: .minute())
        if metrics.contains(.steps) {
            update(try await statistics(.stepCount, unit: .count(), options: .cumulativeSum, start: start, end: end)) { $0.steps = Int($1.rounded()) }
        }
        if metrics.contains(.activeEnergyKcal) {
            update(try await statistics(.activeEnergyBurned, unit: .kilocalorie(), options: .cumulativeSum, start: start, end: end)) {
                $0.activeEnergyKcal = Int($1.rounded())
            }
        }
        if metrics.contains(.restingHeartRate) {
            update(try await statistics(.restingHeartRate, unit: beatsPerMinute, options: .discreteAverage, start: start, end: end)) {
                $0.restingHeartRate = ($1 * 10).rounded() / 10
            }
        }
        if metrics.contains(.hrvMs) {
            update(try await statistics(.heartRateVariabilitySDNN, unit: .secondUnit(with: .milli), options: .discreteAverage,
                                        start: start, end: end)) { $0.hrvMs = ($1 * 10).rounded() / 10 }
        }
        if metrics.contains(.weightKg) {
            update(try await statistics(.bodyMass, unit: .gramUnit(with: .kilo), options: .mostRecent, start: start, end: end)) {
                $0.weightKg = ($1 * 10).rounded() / 10
            }
        }
        if metrics.contains(.vo2Max) {
            update(try await statistics(.vo2Max, unit: HKUnit(from: "ml/kg*min"), options: .mostRecent, start: start, end: end)) {
                $0.vo2Max = ($1 * 10).rounded() / 10
            }
        }
        if metrics.contains(.sleepMinutes) {
            update(try await sleepMinutes(start: start, end: end)) { $0.sleepMinutes = Int($1.rounded()) }
        }
        if metrics.contains(.workoutMinutes) {
            let workouts = try await workoutMinutes(start: start, end: end)
            update(workouts.minutes) { $0.workoutMinutes = Int($1.rounded()) }
            update(workouts.counts) { $0.workoutCount = Int($1) }
        }
        return days.values.filter { !$0.isEmpty }.sorted { $0.date < $1.date }
    }

    // MARK: - queries

    private func statistics(_ identifier: HKQuantityTypeIdentifier, unit: HKUnit, options: HKStatisticsOptions,
                            start: Date, end: Date) async throws -> [Date: Double] {
        let type = HKQuantityType(identifier)
        let predicate = HKQuery.predicateForSamples(withStart: start, end: end)
        let query = HKStatisticsCollectionQueryDescriptor(
            predicate: HKSamplePredicate.quantitySample(type: type, predicate: predicate),
            options: options,
            anchorDate: calendar.startOfDay(for: start),
            intervalComponents: DateComponents(day: 1)
        )
        let collection = try await query.result(for: store)
        var values: [Date: Double] = [:]
        collection.enumerateStatistics(from: start, to: end) { statistics, _ in
            let quantity: HKQuantity?
            if options.contains(.cumulativeSum) {
                quantity = statistics.sumQuantity()
            } else if options.contains(.discreteAverage) {
                quantity = statistics.averageQuantity()
            } else {
                quantity = statistics.mostRecentQuantity()
            }
            if let quantity {
                values[statistics.startDate] = quantity.doubleValue(for: unit)
            }
        }
        return values
    }

    /// Minutes asleep per night, dated by the wake-up day. Overlapping samples (watch and phone) are merged first so
    /// the same minutes are not counted twice.
    private func sleepMinutes(start: Date, end: Date) async throws -> [Date: Double] {
        let predicate = HKQuery.predicateForSamples(withStart: start, end: end)
        let query = HKSampleQueryDescriptor(
            predicates: [HKSamplePredicate.categorySample(type: HKCategoryType(.sleepAnalysis), predicate: predicate)],
            sortDescriptors: [SortDescriptor(\.startDate)]
        )
        let asleep = HKCategoryValueSleepAnalysis.allAsleepValues.map(\.rawValue)
        let intervals = try await query.result(for: store)
            .filter { asleep.contains($0.value) }
            .map { ($0.startDate, $0.endDate) }
            .sorted { $0.0 < $1.0 }
        var merged: [(Date, Date)] = []
        for interval in intervals {
            if let last = merged.last, interval.0 <= last.1 {
                merged[merged.count - 1].1 = max(last.1, interval.1)
            } else {
                merged.append(interval)
            }
        }
        var minutes: [Date: Double] = [:]
        for (from, to) in merged {
            minutes[calendar.startOfDay(for: to), default: 0] += to.timeIntervalSince(from) / 60
        }
        return minutes
    }

    private func workoutMinutes(start: Date, end: Date) async throws -> (minutes: [Date: Double], counts: [Date: Double]) {
        let predicate = HKQuery.predicateForSamples(withStart: start, end: end)
        let query = HKSampleQueryDescriptor(predicates: [HKSamplePredicate.workout(predicate)], sortDescriptors: [])
        var minutes: [Date: Double] = [:]
        var counts: [Date: Double] = [:]
        for workout in try await query.result(for: store) {
            let day = calendar.startOfDay(for: workout.startDate)
            minutes[day, default: 0] += workout.duration / 60
            counts[day, default: 0] += 1
        }
        return (minutes, counts)
    }
}
