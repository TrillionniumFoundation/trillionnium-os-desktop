//! Fixed normal host preparation calls. These source selectors carry no
//! application, Main, file descriptor or completed-operation authority.
use crate::control::{NativeLeafPreparationCase as Case, NativeLeafPreparationMember as Member,
    NativeLeafPreparationRole};
use std::{ffi::OsStr, path::{Component,Path}, process::Command, time::Duration};

const ROOT:&str="/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261126-apps-r2";
const OUTPUT_ROOT:&str="/var/lib/droidloom/qualification/pocket4";
pub const HOST_PREPARATION_SECONDS:u64=1200;

#[derive(Clone,Copy,Debug,Eq,PartialEq)]
pub enum ClockPreparationKind { Timer15, Expiry06, Alarm04 }
impl ClockPreparationKind {
    pub fn name(self)->&'static str {match self {Self::Timer15=>"timer15",Self::Expiry06=>"expiry06",Self::Alarm04=>"alarm04"}}
    pub fn case(self)->Case {if self==Self::Alarm04 {Case::ClockAlarm}else{Case::ClockPair}}
}
#[derive(Clone,Copy,Debug,Eq,PartialEq)]
pub enum NativeCasePreparationStep {
    Identity(NativeLeafPreparationRole),
    Plan(Case),
    ClockSource(ClockPreparationKind),
    ClockBind(ClockPreparationKind),
    DocumentsSource(Case),
    DocumentsPackageHelp(Case),
    DocumentsBind(Case),
}
impl NativeCasePreparationStep {
    pub fn case(self)->Case {
        match self {
            Self::Identity(role)=>role.case(),
            Self::Plan(case)|Self::DocumentsSource(case)|Self::DocumentsPackageHelp(case)|Self::DocumentsBind(case)=>case,
            Self::ClockSource(kind)|Self::ClockBind(kind)=>kind.case(),
        }
    }
    pub fn validate(self)->Result<(),String> {
        let valid=match self {
            Self::Identity(role)=>!matches!(role.case(),Case::GalleryRotation|Case::GalleryVideo|Case::GallerySeek|Case::GalleryAlbum|Case::IhgLondon),
            Self::Plan(case)=>matches!(case,Case::ContactsSearch|Case::CalendarCore|Case::CalendarReminder|Case::CameraPhoto|Case::SettingsSupportedPages),
            Self::DocumentsSource(case)|Self::DocumentsPackageHelp(case)|Self::DocumentsBind(case)=>
                matches!(case,Case::DocumentsSaf|Case::DocumentsSearch),
            Self::ClockSource(_)|Self::ClockBind(_)=>true,
        };
        if valid {Ok(())}else{Err("case has no such normal preparation entry".into())}
    }
    pub fn source_index(self)->Result<usize,String> {
        self.validate()?;
        Ok(match self.case() {
            Case::ContactsSearch|Case::CalendarCore=>0,Case::CalendarReminder=>1,
            Case::CameraPhoto=>2,Case::ClockPair|Case::ClockAlarm=>4,
            Case::DocumentsSaf=>6,Case::DocumentsSearch=>7,Case::SettingsSupportedPages=>13,
            _=>return Err("preparation source index is not defined".into()),
        })
    }
    pub fn entry_relative(self)->Result<&'static str,String> {
        self.validate()?;
        Ok(match self.case() {
            Case::ContactsSearch|Case::CalendarCore=>"source/system/system_entry.py",
            Case::CalendarReminder=>"source/calendar-reminder/system_entry.py",
            Case::CameraPhoto=>"source/camera-photo/camera_entry.py",
            Case::ClockPair|Case::ClockAlarm=>"source/clock/clock_entry.py",
            Case::DocumentsSaf=>"source/documents-saf/documents_entry.py",
            Case::DocumentsSearch=>"source/documents-search/documents_entry.py",
            Case::SettingsSupportedPages=>"source/settings/settings_entry.py",
            _=>return Err("preparation entry absent".into()),
        })
    }
    pub fn preparation_relative(self)->Result<&'static str,String> {
        self.validate()?;
        Ok(match self.case() {
            Case::ContactsSearch|Case::CalendarCore=>"preparations/system.json",
            Case::CalendarReminder=>"preparations/calendar-reminder.json",
            Case::CameraPhoto=>"preparations/camera-photo.json",
            Case::ClockPair|Case::ClockAlarm=>"preparations/clock.json",
            Case::DocumentsSaf=>"preparations/documents-saf.json",
            Case::DocumentsSearch=>"preparations/documents-search.json",
            Case::SettingsSupportedPages=>"preparations/settings.json",
            _=>return Err("preparation input absent".into()),
        })
    }
    pub fn mode(self)->&'static str {
        match self {Self::Identity(_)=>"identity",Self::ClockSource(_)|Self::DocumentsSource(_)=>"source",
            Self::DocumentsPackageHelp(_)=>"pm-help",_=>"plan"}
    }
    pub fn identity_role(self)->Result<Option<&'static str>,String> {
        self.validate()?;
        let Self::Identity(role)=self else{return Ok(None)};
        Ok(Some(match role.member() {
            Member::NativeHelper=>"native-helper",
            Member::Provider=>match role.case() {
                Case::ContactsSearch=>"contacts-provider",Case::CalendarCore|Case::CalendarReminder=>"calendar-provider",
                Case::DocumentsSaf|Case::DocumentsSearch=>"provider",
                _=>return Err("fixed preparation provider absent".into()),
            },
            Member::Application=>match role.case() {
                Case::ContactsSearch=>"contacts",Case::CalendarCore|Case::CalendarReminder=>"calendar",
                Case::CameraPhoto=>"camera",Case::ClockPair|Case::ClockAlarm=>"clock",
                Case::DocumentsSaf|Case::DocumentsSearch=>"documents",Case::SettingsSupportedPages=>"settings",
                _=>return Err("fixed preparation application absent".into()),
            },
            Member::IhgHelper=>return Err("IHG retains its dedicated actual preparation factory".into()),
        }))
    }
    pub fn kind(self)->Option<&'static str> {
        match self {
            Self::Plan(Case::ContactsSearch)=>Some("contacts_search"),
            Self::Plan(Case::CalendarCore)=>Some("calendar_core"),
            Self::Plan(Case::CalendarReminder)=>Some("calendar_reminder"),_=>None,
        }
    }
    pub fn output_prefix(self)->Result<Option<&'static str>,String> {
        self.validate()?;
        Ok(match self {
            Self::Identity(_)=>Some("business-app-identity-"),
            Self::ClockSource(_)=>Some("business-clock-case-"),
            Self::ClockBind(_)|Self::DocumentsBind(_)=>None,
            Self::DocumentsSource(Case::DocumentsSaf)=>Some("business-documents-saf-case-"),
            Self::DocumentsSource(Case::DocumentsSearch)=>Some("business-documents-case-"),
            Self::DocumentsPackageHelp(Case::DocumentsSaf)=>Some("business-documents-saf-pm-help-"),
            Self::DocumentsPackageHelp(Case::DocumentsSearch)=>Some("business-documents-pm-help-"),
            Self::Plan(Case::ContactsSearch)=>Some("business-contacts-search-plan-"),
            Self::Plan(Case::CalendarCore)=>Some("business-calendar-core-plan-"),
            Self::Plan(Case::CalendarReminder)=>Some("business-calendar-reminder-plan-"),
            Self::Plan(Case::CameraPhoto)=>Some("business-camera-photo-plan-"),
            Self::Plan(Case::SettingsSupportedPages)=>Some("business-settings-pages-plan-"),
            _=>return Err("fixed preparation output is undefined".into()),
        })
    }
    pub fn budget(self)->Duration {Duration::from_secs(HOST_PREPARATION_SECONDS)}
    pub(crate) fn check_command(self,command:&Command)->Result<(),String> {
        self.validate()?;
        if command.get_program()!=OsStr::new("/usr/bin/python3") {return Err("preparation must execute the fixed normal Python interpreter".into())}
        let args=command.get_args().map(|s|s.to_str().ok_or("non-UTF8 preparation argument"))
            .collect::<Result<Vec<_>,_>>()?;
        if args.len()<11 || args[..2]!=["-I","-B"]
            || args[2]!=format!("{ROOT}/{}",self.entry_relative()?)
            || args[3]!="--preparation"
            || args[4]!=format!("{ROOT}/{}",self.preparation_relative()?)
            || args[5]!="--expect-preparation-sha256" || !digest(args[6])
            || args[7]!=self.mode() || args[8]!="--request"
            || !request(args[9]) || args[10]!="--expect-request-sha256"
            || args.len()<12 || !digest(args[11]) {
            return Err("preparation arguments differ from the fixed source entry".into())
        }
        let mut cursor=12;
        for (flag,value) in [("--role",self.identity_role()?),("--kind",self.kind())] {
            if let Some(value)=value {
                if args.get(cursor)!=Some(&flag) || args.get(cursor+1)!=Some(&value) {
                    return Err("preparation case/member selector differs".into())
                }
                cursor+=2;
            }
        }
        if let Some(prefix)=self.output_prefix()? {
            if args.get(cursor)!=Some(&"--output") || !args.get(cursor+1).is_some_and(|v|output(v,prefix)) {
                return Err("preparation output is not a new fixed case namespace".into())
            }
            cursor+=2;
        }
        if cursor!=args.len() {return Err("extra preparation command argument".into())}
        Ok(())
    }
}
fn digest(s:&str)->bool {s.len()==64&&s.bytes().all(|c|c.is_ascii_digit()||(b'a'..=b'f').contains(&c))}
fn ordinary(path:&Path)->bool {
    path.is_absolute()&&path.components().all(|c|matches!(c,Component::RootDir|Component::Normal(_)))
}
fn request(value:&str)->bool {
    let path=Path::new(value);
    ordinary(path)&&path.file_name()==Some(OsStr::new("REQUEST.json"))
        &&path.parent().is_some_and(|p|p.parent()==Some(Path::new(OUTPUT_ROOT))
            &&p.file_name().and_then(|s|s.to_str()).is_some_and(|s|
                s.starts_with("native-leaf-")&&s.len()<=80&&s.bytes().all(|b|b.is_ascii_alphanumeric()||b==b'-')))
}
fn output(value:&str,prefix:&str)->bool {
    let path=Path::new(value);
    ordinary(path)&&path.parent()==Some(Path::new(OUTPUT_ROOT))
        &&path.file_name().and_then(|s|s.to_str()).and_then(|s|s.strip_prefix(prefix))
            .is_some_and(|s|s.len()==32&&s.bytes().all(|b|b.is_ascii_digit()||(b'a'..=b'f').contains(&b)))
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn preparation_does_not_expose_execute_or_unimplemented_source_modes() {
        for case in [Case::GalleryRotation,Case::GalleryVideo,Case::GallerySeek,Case::GalleryAlbum,Case::IhgLondon,Case::ClockPair] {
            assert!(NativeCasePreparationStep::Plan(case).validate().is_err());
        }
        assert!(NativeCasePreparationStep::DocumentsSource(Case::ContactsSearch).validate().is_err());
        assert!(request("/var/lib/droidloom/qualification/pocket4/native-leaf-abc123/REQUEST.json"));
        assert!(!request("/var/lib/droidloom/qualification/pocket4/../REQUEST.json"));
        assert!(!output("/tmp/business-app-identity-00000000000000000000000000000000","business-app-identity-"));
    }
    #[test]
    fn preparation_command_binds_the_same_fixed_case_role_and_argument_order() {
        let role=NativeLeafPreparationRole::for_case(Case::ContactsSearch,Member::Provider).unwrap();
        let step=NativeCasePreparationStep::Identity(role);
        let mut good=Command::new("/usr/bin/python3");
        good.args(["-I","-B",&format!("{ROOT}/source/system/system_entry.py"),
            "--preparation",&format!("{ROOT}/preparations/system.json"),
            "--expect-preparation-sha256",&"a".repeat(64),"identity","--request",
            "/var/lib/droidloom/qualification/pocket4/native-leaf-abc123/REQUEST.json",
            "--expect-request-sha256",&"b".repeat(64),"--role","contacts-provider","--output",
            "/var/lib/droidloom/qualification/pocket4/business-app-identity-00000000000000000000000000000000"]);
        step.check_command(&good).unwrap();
        assert!(NativeCasePreparationStep::Identity(
            NativeLeafPreparationRole::for_case(Case::ContactsSearch,Member::Application).unwrap()
        ).check_command(&good).is_err());
        good.arg("--execute");assert!(step.check_command(&good).is_err());
    }
}
