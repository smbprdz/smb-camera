#pragma once
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <mutex>
#include <optional>
#include <utility>

namespace ucs::native {
// One pending value. The caller owns the frame/resource lifetime; retaining
// values after take() is outside this mailbox's allocation budget.
template<class T> class LatestSlot {
    std::mutex mutex_;
    std::condition_variable changed_;
    std::optional<T> value_;
    bool closed_=false;
    std::uint64_t replaced_=0;
public:
    bool put(T value) {
        std::lock_guard lock(mutex_);
        if(closed_)return false;
        if(value_)++replaced_;
        value_=std::move(value);changed_.notify_one();return true;
    }
    template<class Rep,class Period>
    std::optional<T> take_for(std::chrono::duration<Rep,Period> timeout) {
        std::unique_lock lock(mutex_);
        changed_.wait_for(lock,timeout,[this]{return value_.has_value() || closed_;});
        auto result=std::move(value_);value_.reset();return result;
    }
    void close() {
        std::lock_guard lock(mutex_);closed_=true;value_.reset();changed_.notify_all();
    }
    std::uint64_t replaced() {
        std::lock_guard lock(mutex_);return replaced_;
    }
};
} // namespace ucs::native
