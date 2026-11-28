//! Source-fixed original APK subjects for legacy business and preparation.
//! A role names an existing source call site. It is not a PM observation.
use crate::control::ControlError;
use serde::{Deserialize, Serialize};
use std::time::Duration;

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum NativeLeafApkRoute {
    CalendarCore, CalendarReminder, CameraPhoto, ContactsSearch, ClockPair,
    ClockAlarm, DocumentsSaf, DocumentsSearch, GalleryRotation, GalleryVideo,
    GallerySeek, GalleryAlbum, SettingsSupportedPages, IhgLondon,
}
pub type NativeLeafPreparationCase = NativeLeafApkRoute;

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum NativeLeafPreparationMember { Application, Provider, NativeHelper, IhgHelper }

/// Constructible only from one of the fixed case/member pairs. The normal
/// preparation peer and actual PM/Main observations remain separately required.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct NativeLeafPreparationRole {
    case: NativeLeafPreparationCase,
    member: NativeLeafPreparationMember,
}
impl NativeLeafPreparationRole {
    pub fn for_case(case: NativeLeafPreparationCase, member: NativeLeafPreparationMember)
        -> Result<Self, ControlError>
    {
        use NativeLeafPreparationMember as M;
        use NativeLeafApkRoute as C;
        let allowed = match member {
            M::Application => true,
            M::Provider => matches!(case, C::CalendarCore | C::CalendarReminder |
                C::ContactsSearch | C::DocumentsSaf | C::DocumentsSearch),
            M::NativeHelper => case != C::IhgLondon,
            M::IhgHelper => case == C::IhgLondon,
        };
        if !allowed {
            return Err(ControlError::Invalid("preparation case/member has no original identity producer".into()));
        }
        Ok(Self { case, member })
    }
    pub fn apk_begin_seconds(&self) -> u64 { 130 }
    pub fn apk_finish_seconds(&self) -> u64 { 140 }
    pub fn case(&self) -> NativeLeafPreparationCase { self.case }
    pub fn member(&self) -> NativeLeafPreparationMember { self.member }
    pub fn package(&self) -> &'static str {
        // The constructor admits only the fixed pairs above.
        role(self.case, self.member).expect("validated source role").package
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub(crate) enum Scope {
    Business { route: NativeLeafApkRoute },
    Preparation { case: NativeLeafPreparationCase, member: NativeLeafPreparationMember },
}
#[derive(Clone, Copy)]
pub(crate) struct Role {
    pub(crate) member: NativeLeafPreparationMember,
    pub(crate) package: &'static str,
    pub(crate) max_apks: usize,
    pub(crate) max_bytes: u64,
}
const MIB: u64 = 1024 * 1024;
pub(crate) const MAX_GROUP_APKS: usize = 34;
pub(crate) const MAX_GROUP_BYTES: u64 = 1024 * MIB + 17 * MIB;
const NATIVE: &str = "local.pocket4.actions.v2";
const MEDIA: &str = "com.android.providers.media.module";

impl NativeLeafApkRoute {
    pub fn package(self) -> &'static str {
        use NativeLeafApkRoute as C;
        match self {
            C::CalendarCore | C::CalendarReminder => "com.android.calendar",
            C::CameraPhoto => "com.android.camera2",
            C::ContactsSearch => "com.android.contacts",
            C::ClockPair | C::ClockAlarm => "com.android.deskclock",
            C::DocumentsSaf | C::DocumentsSearch => "com.android.documentsui",
            C::GalleryRotation | C::GalleryVideo | C::GallerySeek | C::GalleryAlbum => "com.android.gallery3d",
            C::SettingsSupportedPages => "com.android.settings",
            C::IhgLondon => "com.ihg.apps.android",
        }
    }
    pub fn apk_begin_seconds(self) -> u64 { Scope::Business { route: self }.begin_seconds() }
    pub fn apk_finish_seconds(self) -> u64 { Scope::Business { route: self }.finish_seconds() }
}
fn role(case: NativeLeafApkRoute, member: NativeLeafPreparationMember) -> Option<Role> {
    use NativeLeafApkRoute as C;
    use NativeLeafPreparationMember as M;
    let (package, max_apks, max_bytes) = match member {
        M::Application => (case.package(), 32, 1024 * MIB),
        M::NativeHelper if case != C::IhgLondon => (NATIVE, 1, MIB),
        M::IhgHelper if case == C::IhgLondon =>
            ("org.droidloom.qa.ihg.finalmain.r1", 1, 2 * MIB),
        M::Provider => {
            let package = match case {
                C::CalendarCore | C::CalendarReminder => "com.android.providers.calendar",
                C::ContactsSearch => "com.android.providers.contacts",
                C::DocumentsSaf | C::DocumentsSearch => "com.android.externalstorage",
                C::CameraPhoto | C::GalleryRotation => MEDIA,
                _ => return None,
            };
            (package, 1, 16 * MIB)
        }
        _ => return None,
    };
    Some(Role { member, package, max_apks, max_bytes })
}
impl Scope {
    pub(crate) fn preparation(role: NativeLeafPreparationRole) -> Self {
        Self::Preparation { case: role.case, member: role.member }
    }
    pub(crate) fn validate(self) -> Result<(), String> {
        if let Self::Preparation { case, member } = self {
            NativeLeafPreparationRole::for_case(case, member).map_err(|e| e.to_string())?;
        }
        let roles = self.roles();
        super::apk_protocol::need(!roles.is_empty() && roles.len() <= 3
            && roles.iter().enumerate().all(|(i, r)| roles[..i].iter().all(|p| p.package != r.package)),
            "APK fixed source group differs")
    }
    pub(crate) fn is_preparation(self) -> bool { matches!(self, Self::Preparation { .. }) }
    pub(crate) fn subject_package(self) -> &'static str { self.roles()[0].package }
    pub(crate) fn roles(self) -> Vec<Role> {
        use NativeLeafApkRoute as C;
        use NativeLeafPreparationMember as M;
        match self {
            Self::Preparation { case, member } => role(case, member).into_iter().collect(),
            Self::Business { route } => {
                let mut members = vec![M::Application];
                if matches!(route, C::CalendarCore | C::CalendarReminder | C::CameraPhoto |
                    C::ContactsSearch | C::DocumentsSaf | C::DocumentsSearch | C::GalleryRotation) {
                    members.push(M::Provider);
                }
                members.push(if route == C::IhgLondon { M::IhgHelper } else { M::NativeHelper });
                members.into_iter().map(|m| role(route, m).expect("fixed original business role")).collect()
            }
        }
    }
    pub(crate) fn begin_seconds(self) -> u64 { 70 * self.roles().len() as u64 + 60 }
    pub(crate) fn finish_seconds(self) -> u64 { 70 * self.roles().len() as u64 + 70 }
    pub(crate) fn metadata_cap(self) -> Duration { Duration::from_secs(70 * self.roles().len() as u64) }
    pub(crate) fn begin_cap(self) -> Duration { Duration::from_secs(self.begin_seconds()) }
    pub(crate) fn finish_cap(self) -> Duration { Duration::from_secs(self.finish_seconds()) }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn native_leaf_apk_scope_keeps_existing_roles_and_preparation_distinct() {
        use NativeLeafApkRoute as C;
        use NativeLeafPreparationMember as M;
        let routes = [C::CalendarCore,C::CalendarReminder,C::CameraPhoto,C::ContactsSearch,
            C::ClockPair,C::ClockAlarm,C::DocumentsSaf,C::DocumentsSearch,C::GalleryRotation,
            C::GalleryVideo,C::GallerySeek,C::GalleryAlbum,C::SettingsSupportedPages,C::IhgLondon];
        let counts = [3,3,3,3,2,2,3,3,3,2,2,2,2,2];
        for (ordinal, (case, count)) in routes.into_iter().zip(counts).enumerate() {
            let scope=Scope::Business{route:case}; scope.validate().unwrap();
            assert_eq!(scope.roles().len(),count);
            assert_eq!(scope.begin_seconds(),crate::control::physical_qualification_channel::budget::native_apk_begin_seconds(ordinal));
            assert_eq!(scope.finish_seconds(),crate::control::physical_qualification_channel::budget::native_apk_finish_seconds(ordinal));
            assert_eq!(scope.subject_package(),case.package());
            assert_eq!(scope.begin_seconds()+scope.finish_seconds(),140*count as u64+130);
            assert!(NativeLeafPreparationRole::for_case(case,M::Application).is_ok());
        }
        assert!(NativeLeafPreparationRole::for_case(C::CameraPhoto,M::Provider).is_err());
        assert!(NativeLeafPreparationRole::for_case(C::GalleryRotation,M::Provider).is_err());
        assert!(NativeLeafPreparationRole::for_case(C::IhgLondon,M::NativeHelper).is_err());
        assert!(NativeLeafPreparationRole::for_case(C::ContactsSearch,M::IhgHelper).is_err());
        let role=NativeLeafPreparationRole::for_case(C::ContactsSearch,M::Provider).unwrap();
        let prep=Scope::preparation(role);
        assert_eq!(prep.subject_package(),"com.android.providers.contacts");
        assert_eq!(prep.roles().len(),1);
        assert_ne!(prep,Scope::Business{route:C::ContactsSearch});
    }
}

pub(crate) fn known_package(package:&str)->bool {
    use NativeLeafApkRoute as C;
    [C::CalendarCore,C::CalendarReminder,C::CameraPhoto,C::ContactsSearch,C::ClockPair,C::ClockAlarm,
        C::DocumentsSaf,C::DocumentsSearch,C::GalleryRotation,C::GalleryVideo,C::GallerySeek,C::GalleryAlbum,
        C::SettingsSupportedPages,C::IhgLondon].into_iter()
        .any(|route|Scope::Business{route}.roles().iter().any(|role|role.package==package))
}
