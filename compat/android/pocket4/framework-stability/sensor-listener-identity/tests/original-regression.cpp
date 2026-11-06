// Host regression adapter: real AOSP sp/LightRefBase and exact production methods.
// Binder transport, IPC identity, logging and unrelated SensorService fields are test doubles.
#include <atomic>
#include <algorithm>
#include <cassert>
#include <condition_variable>
#include <cstdlib>
#include <functional>
#include <iostream>
#include <memory>
#include <mutex>
#include <set>
#include <stdexcept>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>
#include <utils/LightRefBase.h>
#include <utils/StrongPointer.h>
#define ALOGW(...) do {} while (0)
#define ALOGE(...) do {} while (0)
#define ALOGD(...) do {} while (0)
#define ALOGI(...) do {} while (0)
#define GUARDED_BY(x)
namespace android {
void sp_report_race() { std::abort(); }
void LightRefBase_reportIncStrongRequireStrongFailed(const void*) { std::abort(); }
using status_t=int;
constexpr status_t OK=0, INVALID_OPERATION=-38, BAD_VALUE=-22, ALREADY_EXISTS=-17,
        UNKNOWN_TRANSACTION=-74, NAME_NOT_FOUND=-2, DEAD_OBJECT=-32;
namespace hardware { namespace flags {
std::atomic<bool> enabled{true};
bool suspend_sensor_event_delivery_on_frozen_pid() { return enabled.load(); }
}}
class Mutex {
public:
    std::mutex native;
    static inline thread_local int held=0;
    class Autolock {
        Mutex& m;
    public:
        explicit Autolock(Mutex& value):m(value) {m.native.lock();++held;}
        ~Autolock() {--held;m.native.unlock();}
    };
};
class IPCThreadState {
public:
    static IPCThreadState* self() { static IPCThreadState instance;return &instance;}
    pid_t getCallingPid() const {return 77;}
    uid_t getCallingUid() const {return 10061;}
};
class IBinder : public VirtualLightRefBase {
public:
    std::mutex transport;
    std::set<const void*> deaths, frozen;
    int link_calls=0, add_calls=0, unlink_calls=0, remove_calls=0;
    int link_error=OK, add_error=OK, remove_error=OK;
    bool all_link_locked=true, all_add_locked=true;
    std::vector<bool> unlink_lock_state, remove_lock_state;
    std::function<void()> before_unlink;
    template<class T> status_t linkToDeath(const sp<T>& who) {
        std::lock_guard<std::mutex> lock(transport);
        ++link_calls;all_link_locked &= Mutex::held>0;
        if(link_error!=OK)return link_error;
        if(!deaths.insert(who.get()).second)throw std::runtime_error("DOUBLE_DEATH_RECIPIENT");
        return OK;
    }
    template<class T> status_t addFrozenStateChangeCallback(const sp<T>& who) {
        std::lock_guard<std::mutex> lock(transport);
        ++add_calls;all_add_locked &= Mutex::held>0;
        if(add_error!=OK)return add_error;
        if(!frozen.insert(who.get()).second)throw std::runtime_error("DOUBLE_FROZEN_RECIPIENT");
        return OK;
    }
    template<class T> status_t unlinkToDeath(const sp<T>& who) {
        if(before_unlink)before_unlink();
        std::lock_guard<std::mutex> lock(transport);
        ++unlink_calls;unlink_lock_state.push_back(Mutex::held>0);
        return deaths.erase(who.get()) ? OK : NAME_NOT_FOUND;
    }
    template<class T> status_t removeFrozenStateChangeCallback(const sp<T>& who) {
        std::lock_guard<std::mutex> lock(transport);
        ++remove_calls;remove_lock_state.push_back(Mutex::held>0);
        auto n=frozen.erase(who.get());
        return remove_error!=OK ? remove_error : (n?OK:NAME_NOT_FOUND);
    }
    size_t frozenCount() {std::lock_guard<std::mutex> lock(transport);return frozen.size();}
    size_t deathCount() {std::lock_guard<std::mutex> lock(transport);return deaths.size();}
};
class IInterface : public VirtualLightRefBase {
protected: virtual IBinder* onAsBinder()=0;
public:
    static sp<IBinder> asBinder(const sp<IInterface>& iface) {
        if(iface==nullptr)return nullptr;
        return sp<IBinder>::fromExisting(iface->onAsBinder());
    }
};
namespace hardware { namespace sensor {
class ISensorClientListener : public IInterface {
    sp<IBinder> binder;
protected: IBinder* onAsBinder() override {return binder.get();}
public: explicit ISensorClientListener(const sp<IBinder>& b):binder(b){}
};
}}

struct SensorClientListenerHasher {
    size_t operator()(const sp<hardware::sensor::ISensorClientListener>& listener) const {
        return std::hash<hardware::sensor::ISensorClientListener*>()(listener.get());
    }
};


class SensorService {
public:
    class ClientStateRecipient : public VirtualLightRefBase {
        sp<hardware::sensor::ISensorClientListener> mListener;
        pid_t mPid;
    public:
        static inline std::atomic<int> alive{0};
        ClientStateRecipient(SensorService*,const sp<hardware::sensor::ISensorClientListener>& listener,pid_t pid,uid_t)
            :mListener(listener),mPid(pid) {++alive;}
        ~ClientStateRecipient() override {--alive;}
        pid_t getPid() const {return mPid;}
        const auto& listener() const {return mListener;}
    };
    mutable Mutex mBinderStateRecipientsLock;
    std::unordered_map<sp<hardware::sensor::ISensorClientListener>, sp<ClientStateRecipient>,
                       SensorClientListenerHasher>
            mBinderStateRecipients GUARDED_BY(mBinderStateRecipientsLock);
    struct Policy {void unregisterSelf(){}};
    std::unique_ptr<Policy> mUidPolicy=std::make_unique<Policy>();
    std::unique_ptr<Policy> mSensorPrivacyPolicy=std::make_unique<Policy>();
    std::unique_ptr<Policy> mMicSensorPrivacyPolicy=std::make_unique<Policy>();
    std::unordered_map<int,int*> mRecentEvent;
    status_t registerClientListener(const sp<hardware::sensor::ISensorClientListener>&);
    status_t unregisterClientListener(const sp<hardware::sensor::ISensorClientListener>&);
    void onClientDied(const sp<hardware::sensor::ISensorClientListener>&);
    ~SensorService();
    size_t entries() {Mutex::Autolock lock(mBinderStateRecipientsLock);return mBinderStateRecipients.size();}
};

status_t SensorService::registerClientListener(
        const sp<android::hardware::sensor::ISensorClientListener>& listener) {
    if (!android::hardware::flags::suspend_sensor_event_delivery_on_frozen_pid()) {
        return INVALID_OPERATION;
    }
    if (listener == nullptr) {
        return BAD_VALUE;
    }

    pid_t pid = IPCThreadState::self()->getCallingPid();
    uid_t uid = IPCThreadState::self()->getCallingUid();

    Mutex::Autolock _l(mBinderStateRecipientsLock);

    if (mBinderStateRecipients.count(listener)) {
        ALOGW("Listener already registered (pid=%d, uid=%d). Ignoring duplicate registration.", pid,
              uid);
        return ALREADY_EXISTS;
    }

    sp<ClientStateRecipient> recipient = new ClientStateRecipient(this, listener, pid, uid);
    sp<IBinder> binder = IInterface::asBinder(listener);

    status_t err = binder->linkToDeath(recipient);
    if (err != OK) {
        ALOGW("Failed to linkToDeath for listener (pid=%d, uid=%d), error=%d. "
              "Aborting registration.",
              pid, uid, err);
        return err;
    }

    status_t frozenErr = binder->addFrozenStateChangeCallback(recipient);
    if (frozenErr != OK) {
        ALOGE("Failed to addFrozenStateChangeCallback (pid=%d, uid=%d), error=%d. "
              "Cleaning up linkToDeath and aborting registration.",
              pid, uid, frozenErr);
        binder->unlinkToDeath(recipient); // Rollback linkToDeath
        return frozenErr;
    }

    mBinderStateRecipients[listener] = recipient;

    return OK;
}

status_t SensorService::unregisterClientListener(
        const sp<android::hardware::sensor::ISensorClientListener>& listener) {
    if (!android::hardware::flags::suspend_sensor_event_delivery_on_frozen_pid()) {
        return UNKNOWN_TRANSACTION;
    }

    if (listener == nullptr) {
        return BAD_VALUE;
    }

    sp<IBinder> binder = IInterface::asBinder(listener);
    if (binder == nullptr) {
        return BAD_VALUE;
    }

    sp<ClientStateRecipient> recipient;
    {
        Mutex::Autolock _l(mBinderStateRecipientsLock);

        auto it = mBinderStateRecipients.find(listener);
        if (it != mBinderStateRecipients.end()) {
            recipient = it->second;
            mBinderStateRecipients.erase(it);
            ALOGD("Unregistering client listener for PID %d", recipient->getPid());
        } else {
            return NAME_NOT_FOUND;
        }
    }

    if (recipient != nullptr) {
        // Detach from binder notifications. Do this without holding mStateLock to prevent ANR.
        binder->unlinkToDeath(recipient);
        status_t removeErr = binder->removeFrozenStateChangeCallback(recipient);
        if (removeErr != OK && removeErr != DEAD_OBJECT) {
            // DEAD_OBJECT is expected if the client is already gone.
            ALOGW("Failed to remove frozen state change callback, error=%d", removeErr);
        }
    }
    return OK;
}

void SensorService::onClientDied(const sp<hardware::sensor::ISensorClientListener>& listener) {
    if (!android::hardware::flags::suspend_sensor_event_delivery_on_frozen_pid()) {
        return;
    }
    unregisterClientListener(listener);
}

SensorService::~SensorService() {
    ALOGI("SensorService destructor starting");
    if (android::hardware::flags::suspend_sensor_event_delivery_on_frozen_pid()) {

        std::vector<sp<hardware::sensor::ISensorClientListener>> listenersToUnregister;
        {
            Mutex::Autolock _l(mBinderStateRecipientsLock);
            listenersToUnregister.reserve(mBinderStateRecipients.size());
            for (const auto& pair : mBinderStateRecipients) {
                listenersToUnregister.push_back(pair.first);
            }
        }

        if (!listenersToUnregister.empty()) {
            ALOGI("Unregistering %zu client listeners during shutdown.",
                  listenersToUnregister.size());
            for (const auto& listener : listenersToUnregister) {
                // unregisterClientListener locks mStateLock internally, but it's fine as
                // the destructor does not hold the lock in this loop.
                unregisterClientListener(listener);
            }
            ALOGI("Finished unregistering all client listeners.");
        }
    }

    for (auto && entry : mRecentEvent) {
        delete entry.second;
    }
    mUidPolicy->unregisterSelf();
    mSensorPrivacyPolicy->unregisterSelf();
    mMicSensorPrivacyPolicy->unregisterSelf();
}


} // namespace android
using namespace android;
using Listener=hardware::sensor::ISensorClientListener;
constexpr bool candidate=EXPECT_CANDIDATE;
void must(bool condition,const char* message) {if(!condition)throw std::runtime_error(message);}
sp<Listener> wrap(const sp<IBinder>& binder) {return sp<Listener>::make(binder);}
struct Runner {
    int cases=0, unexpected=0, reproduced=0;
    void run(const char* name,bool baselineDefect,const std::function<bool()>& body) {
        bool contract=false;std::string error;
        try {contract=body();if(!contract&&(candidate||!baselineDefect))throw std::runtime_error("CONTRACT_NOT_SATISFIED");}
        catch(const std::exception& e){error=e.what();++unexpected;}
        ++cases;
        if(!candidate&&baselineDefect&&!contract&&error.empty())++reproduced;
        std::cout<<"{\"case\":\""<<name<<"\",\"contract_satisfied\":"<<(contract?"true":"false")
                 <<",\"expected_baseline_defect\":"<<((!candidate&&baselineDefect&&!contract&&error.empty())?"true":"false")
                 <<",\"error\":\""<<error<<"\"}\n";
        must(SensorService::ClientStateRecipient::alive.load()==0,"RECIPIENT_RETAINED_AFTER_CASE");
        hardware::flags::enabled=true;
    }
};
int main() {
    Runner r;
    r.run("same_wrapper_duplicate_no_extra_callback",false,[]{
        auto b=sp<IBinder>::make();auto a=wrap(b);
        SensorService s;
        must(s.registerClientListener(a)==OK,"FIRST_REGISTER");
        must(s.registerClientListener(a)==ALREADY_EXISTS,"SAME_WRAPPER_DUP");
        must(s.entries()==1&&b->add_calls==1&&b->link_calls==1,"DUP_TRANSPORT");
        must(s.unregisterClientListener(a)==OK,"UNREGISTER");
        return b->frozenCount()==0&&b->deathCount()==0;
    });
    r.run("fresh_wrapper_same_binder_deduplicates",true,[]{
        auto b=sp<IBinder>::make();auto a=wrap(b),another=wrap(b);
        must(a.get()!=another.get()&&IInterface::asBinder(a)==IInterface::asBinder(another),"WRAPPER_FIXTURE");
        SensorService s;
        must(s.registerClientListener(a)==OK,"FIRST_REGISTER");
        int second=s.registerClientListener(another);
        size_t entries=s.entries();int callbacks=b->add_calls;
        must(second==(candidate?ALREADY_EXISTS:OK),"DUP_STATUS");
        must(entries==(candidate?1:2)&&callbacks==(candidate?1:2),"DUP_OBSERVATION");
        return second==ALREADY_EXISTS&&entries==1&&callbacks==1;
    });
    r.run("unregister_fresh_wrapper_same_binder",true,[]{
        auto b=sp<IBinder>::make();auto a=wrap(b);
        SensorService s;must(s.registerClientListener(a)==OK,"REGISTER");
        int status=s.unregisterClientListener(wrap(b));
        size_t entries=s.entries(), callbacks=b->frozenCount();
        must(status==(candidate?OK:NAME_NOT_FOUND),"UNREGISTER_STATUS");
        must(entries==(candidate?0:1)&&callbacks==(candidate?0:1),"UNREGISTER_OBSERVATION");
        return status==OK&&entries==0&&callbacks==0;
    });
    r.run("64_fresh_wrappers_keep_one_recipient",true,[]{
        auto b=sp<IBinder>::make();SensorService s;
        int accepted=0,duplicate=0;
        for(int i=0;i<64;++i){int x=s.registerClientListener(wrap(b));accepted+=x==OK;duplicate+=x==ALREADY_EXISTS;}
        auto entries=s.entries();int retainedBinderStrong=b->getStrongCount();
        must(accepted==(candidate?1:64)&&duplicate==(candidate?63:0),"REPEATED_STATUSES");
        must(entries==(candidate?1:64)&&b->frozenCount()==entries,"REPEATED_RECIPIENTS");
        must(retainedBinderStrong==(candidate?2:65),"CANONICAL_BINDER_LIFETIME");
        std::cout<<"{\"metric\":\"repeated_registration\",\"accepted\":"<<accepted
                 <<",\"duplicate\":"<<duplicate<<",\"entries\":"<<entries
                 <<",\"retained_binder_strong\":"<<retainedBinderStrong<<"}\n";
        return accepted==1&&entries==1&&retainedBinderStrong==2;
    });
    r.run("16_concurrent_fresh_wrappers_one_registration",true,[]{
        auto b=sp<IBinder>::make();SensorService s;
        std::atomic<int> accepted{0},duplicate{0},other{0};
        std::vector<std::thread> workers;
        for(int i=0;i<16;++i)workers.emplace_back([&]{int x=s.registerClientListener(wrap(b));if(x==OK)++accepted;else if(x==ALREADY_EXISTS)++duplicate;else ++other;});
        for(auto& w:workers)w.join();
        must(other==0&&accepted==(candidate?1:16)&&duplicate==(candidate?15:0),"CONCURRENT_STATUSES");
        must(s.entries()==size_t(accepted.load())&&b->add_calls==accepted.load(),"CONCURRENT_TRANSPORT");
        return accepted==1&&duplicate==15;
    });
    r.run("distinct_binders_same_pid_remain_distinct",false,[]{
        auto b1=sp<IBinder>::make(),b2=sp<IBinder>::make();
        auto a=wrap(b1),b=wrap(b2);SensorService s;
        must(s.registerClientListener(a)==OK&&s.registerClientListener(b)==OK,"TWO_BINDERS");
        must(s.entries()==2,"PID_NOT_IDENTITY");
        must(s.unregisterClientListener(a)==OK&&b2->frozenCount()==1,"INDEPENDENT_REMOVE");
        return s.unregisterClientListener(b)==OK&&s.entries()==0;
    });
    r.run("null_listener_rejected",false,[]{
        SensorService s;sp<Listener> empty;
        return s.registerClientListener(empty)==BAD_VALUE&&s.unregisterClientListener(empty)==BAD_VALUE&&s.entries()==0;
    });
    r.run("disabled_feature_no_callbacks",false,[]{
        hardware::flags::enabled=false;
        auto b=sp<IBinder>::make();SensorService s;
        return s.registerClientListener(wrap(b))==INVALID_OPERATION
            &&s.unregisterClientListener(wrap(b))==UNKNOWN_TRANSACTION&&s.entries()==0&&b->link_calls==0;
    });
    r.run("death_link_failure_no_partial_entry",false,[]{
        auto b=sp<IBinder>::make();b->link_error=DEAD_OBJECT;SensorService s;
        return s.registerClientListener(wrap(b))==DEAD_OBJECT&&s.entries()==0
            &&b->add_calls==0&&b->deathCount()==0&&b->frozenCount()==0;
    });
    r.run("frozen_callback_failure_rolls_back_death_link",false,[]{
        auto b=sp<IBinder>::make();b->add_error=INVALID_OPERATION;SensorService s;
        int status=s.registerClientListener(wrap(b));
        return status==INVALID_OPERATION&&s.entries()==0&&b->unlink_calls==1
            &&b->deathCount()==0&&b->frozenCount()==0
            &&b->unlink_lock_state==std::vector<bool>{true};
    });
    r.run("registration_after_transport_failure",false,[]{
        auto b=sp<IBinder>::make();b->add_error=INVALID_OPERATION;SensorService s;
        must(s.registerClientListener(wrap(b))==INVALID_OPERATION,"EXPECTED_FAILURE");
        b->add_error=OK;auto a=wrap(b);
        must(s.registerClientListener(a)==OK,"SECOND_NEW_ATTEMPT");
        return s.entries()==1&&s.unregisterClientListener(a)==OK&&b->frozenCount()==0;
    });
    r.run("normal_unregistration_removes_outside_map_lock",false,[]{
        auto b=sp<IBinder>::make();auto a=wrap(b);SensorService s;
        must(s.registerClientListener(a)==OK,"REGISTER");
        must(s.unregisterClientListener(a)==OK,"UNREGISTER");
        return b->all_link_locked&&b->all_add_locked
            &&b->unlink_lock_state==std::vector<bool>{false}
            &&b->remove_lock_state==std::vector<bool>{false};
    });
    r.run("second_unregistration_has_no_extra_effect",false,[]{
        auto b=sp<IBinder>::make();auto a=wrap(b);SensorService s;
        must(s.registerClientListener(a)==OK&&s.unregisterClientListener(a)==OK,"FIRST_PAIR");
        return s.unregisterClientListener(a)==NAME_NOT_FOUND&&b->unlink_calls==1&&b->remove_calls==1;
    });
    r.run("death_cleanup_uses_original_listener",false,[]{
        auto b=sp<IBinder>::make();auto a=wrap(b);SensorService s;
        must(s.registerClientListener(a)==OK,"REGISTER");s.onClientDied(a);
        return s.entries()==0&&b->frozenCount()==0&&b->deathCount()==0;
    });
    r.run("dead_remote_during_unregistration",false,[]{
        auto b=sp<IBinder>::make();auto a=wrap(b);SensorService s;
        must(s.registerClientListener(a)==OK,"REGISTER");b->remove_error=DEAD_OBJECT;
        return s.unregisterClientListener(a)==OK&&s.entries()==0&&b->frozenCount()==0;
    });
    r.run("destructor_cleans_every_owned_recipient",false,[]{
        auto b=sp<IBinder>::make(),c=sp<IBinder>::make();
        {SensorService s;must(s.registerClientListener(wrap(b))==OK,"B_REGISTER");
         must(s.registerClientListener(wrap(c))==OK,"C_REGISTER");}
        return b->deathCount()==0&&b->frozenCount()==0&&c->deathCount()==0&&c->frozenCount()==0;
    });
    r.run("new_registration_during_old_unlink_keeps_new_callback",false,[]{
        auto b=sp<IBinder>::make();auto a=wrap(b),fresh=wrap(b);SensorService s;
        must(s.registerClientListener(a)==OK,"OLD_REGISTER");
        std::mutex sync;std::condition_variable cv;bool entered=false,release=false;
        b->before_unlink=[&]{std::unique_lock<std::mutex> l(sync);entered=true;cv.notify_one();cv.wait(l,[&]{return release;});};
        int removeStatus=123;std::thread worker([&]{removeStatus=s.unregisterClientListener(a);});
        {std::unique_lock<std::mutex> l(sync);cv.wait(l,[&]{return entered;});}
        int newStatus=s.registerClientListener(fresh);
        size_t during=b->frozenCount();
        {std::lock_guard<std::mutex> l(sync);release=true;}cv.notify_one();worker.join();
        b->before_unlink={};
        must(removeStatus==OK&&newStatus==OK&&during==2,"UNLINK_INTERLEAVING");
        must(s.entries()==1&&b->frozenCount()==1&&b->deathCount()==1,"NEW_RECIPIENT_SURVIVES");
        return s.unregisterClientListener(fresh)==OK&&b->frozenCount()==0;
    });
    std::cout<<"{\"summary\":\""<<(candidate?"CANDIDATE_CONTRACTS_PASS":"BASELINE_DEFECT_REPRODUCED")
             <<"\",\"cases\":"<<r.cases<<",\"unexpected\":"<<r.unexpected
             <<",\"baseline_defects_reproduced\":"<<r.reproduced<<"}\n";
    return r.unexpected==0&&(candidate||r.reproduced==4)?0:1;
}
