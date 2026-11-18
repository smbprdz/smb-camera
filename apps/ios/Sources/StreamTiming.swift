import Foundation

/// Four-timestamp estimate, desktop-minus-phone clock offset. Not glass-to-glass latency.
struct ClockEstimate {
    private(set) var offsetUs: Double?
    private(set) var uncertaintyUs: Double?
    mutating func observe(t1:UInt64,t2:UInt64,t3:UInt64,t4:UInt64) {
        guard t4 >= t1, t3 >= t2 else { return }
        let roundTrip = Double(t4-t1)-Double(t3-t2)
        guard roundTrip >= 0, roundTrip <= 5_000_000 else { return }
        if uncertaintyUs == nil || roundTrip/2 < uncertaintyUs! {
            offsetUs = ((Double(t2)-Double(t1))+(Double(t3)-Double(t4)))/2
            uncertaintyUs = roundTrip/2
        }
    }
}
