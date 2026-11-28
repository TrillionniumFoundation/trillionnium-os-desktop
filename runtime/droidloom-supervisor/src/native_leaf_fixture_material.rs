//! Fixed public fixture material. This custody contains no installation or
//! Android authority. Only the normal transaction can create a late-born owner.
use crate::production_application::apk_scope::NativeLeafApkRoute;
use crate::prebuilt_native_helpers::{HelperKind,PrebuiltStateMaterial};
use serde::{Deserialize,Serialize};
use serde_json::{Value,json};
use std::{fs::File,io,time::Instant};

#[derive(Clone,Copy,Debug,Eq,PartialEq,Serialize,Deserialize)]
#[serde(rename_all="snake_case")]
pub(crate) enum NativeLeafFixtureKind {
    DocumentsSaf, DocumentsFeatures, GalleryRotation, GalleryVideo,
}
impl NativeLeafFixtureKind {
    pub(crate) fn for_route(route:NativeLeafApkRoute)->io::Result<Self>{
        use NativeLeafApkRoute as R;
        match route{
            R::DocumentsSaf=>Ok(Self::DocumentsSaf),R::DocumentsSearch=>Ok(Self::DocumentsFeatures),
            R::GalleryRotation=>Ok(Self::GalleryRotation),
            R::GalleryVideo|R::GallerySeek|R::GalleryAlbum=>Ok(Self::GalleryVideo),
            _=>Err(bad("this source route has no late-born fixture transaction")),
        }
    }
    pub(crate) const fn package(self)->&'static str{match self{
        Self::DocumentsSaf=>"org.droidloom.qa.saf.r12.na7f1de49e707c7a9",
        Self::DocumentsFeatures=>"org.droidloom.qa.documents.r12.n98116f3fbefcfc95",
        Self::GalleryRotation=>"org.droidloom.qa.galleryrotation.r12.nd24b61ed8f7c9a03",
        Self::GalleryVideo=>"org.droidloom.qa.media.r12.nc92c3d79180955ef",
    }}
    pub(crate) const fn run_id(self)->&'static str{match self{
        Self::DocumentsSaf=>"a7f1de49e707c7a9",Self::DocumentsFeatures=>"98116f3fbefcfc95",
        Self::GalleryRotation=>"d24b61ed8f7c9a03",Self::GalleryVideo=>"c92c3d79180955ef",
    }}
    pub(crate) const fn version_code(self)->u64{1}
    pub(crate) const fn preference_name(self)->&'static str{match self{
        Self::DocumentsSaf=>"owned-saf-a7f1de49e707c7a9.xml",
        Self::DocumentsFeatures=>"owned-features-98116f3fbefcfc95.xml",
        Self::GalleryRotation=>"owned-rotation-d24b61ed8f7c9a03.xml",
        Self::GalleryVideo=>"owned-media-c92c3d79180955ef-video.xml",
    }}
    pub(crate) const fn apk_bytes(self)->u64{match self{
        Self::DocumentsSaf=>24838,Self::DocumentsFeatures=>24838,
        Self::GalleryRotation=>24838,Self::GalleryVideo=>41286,
    }}
    pub(crate) const fn apk_sha256(self)->&'static str{match self{
        Self::DocumentsSaf=>"eb7bac9ede6b729829fbecb031db4ae7b7224634619154abe2f01b2b3be875d6",
        Self::DocumentsFeatures=>"368e9c52f391c0f11f78da4b1c3c9e72abe31f4d001fa593ebd46a59dcb7fab5",
        Self::GalleryRotation=>"d53ba35fdb2252126fef94ce7da2d43bff78560cc90111206b0c2c9e766777d3",
        Self::GalleryVideo=>"f47d64fe943bb77fb8ad07288b4ae1c69e3db8cc8866b0e02230882134599820",
    }}
    pub(crate) const fn certificate_sha256(self)->&'static str{match self{
        Self::DocumentsSaf=>"b5ed86bf8873ade11e2304965288d19f0ee0dc84da5a5f3e4411d4535b015ea7",
        Self::DocumentsFeatures=>"06c090f9bcca6c214621b85222ddc86d672aee3085c1e3bc278a40f8c5d8ef11",
        Self::GalleryRotation=>"f122e9201c86a547b8cbaa37cbe2cd7962bb96eabe3c07365204d392b580244f",
        Self::GalleryVideo=>"011632c9e2a1693585594df2bcc4b4fdb4cd074a05ccbdc5aa951aa1de9ad0b2",
    }}
    fn normal_kind(self)->HelperKind{match self{
        Self::DocumentsSaf=>HelperKind::Saf,Self::DocumentsFeatures=>HelperKind::Features,
        Self::GalleryRotation=>HelperKind::Rotation,Self::GalleryVideo=>HelperKind::Video,
    }}
}

fn bad(s:&str)->io::Error{io::Error::new(io::ErrorKind::InvalidData,s)}
fn before(end:Instant)->io::Result<()>{
    if Instant::now()>=end{Err(bad("fixture material original deadline elapsed"))}else{Ok(())}
}
/// The actual material FD and protected directory chain remain held; a saved
/// build report or hash cannot construct this type or create a fixture.
pub(crate) struct NativeLeafFixtureMaterial{kind:NativeLeafFixtureKind,held:PrebuiltStateMaterial,end:Instant}
impl NativeLeafFixtureMaterial{
    pub(crate) fn capture(kind:NativeLeafFixtureKind,end:Instant)->io::Result<Self>{
        Self::capture_before(kind,end,end)
    }
    pub(crate) fn capture_before(kind:NativeLeafFixtureKind,retention_end:Instant,end:Instant)->io::Result<Self>{
        if end>retention_end{return Err(bad("fixture capture operation exceeds original retention end"));}
        before(end)?;
        let held=PrebuiltStateMaterial::capture_before(kind.normal_kind(),retention_end,end)?;
        let value=Self{kind,held,end:retention_end};value.guard(end)?;Ok(value)
    }
    pub(crate) fn kind(&self)->NativeLeafFixtureKind{self.kind}
    pub(crate) fn package(&self)->&'static str{self.kind.package()}
    pub(crate) fn run_id(&self)->&'static str{self.kind.run_id()}
    pub(crate) fn version_code(&self)->u64{self.kind.version_code()}
    pub(crate) fn apk_bytes(&self)->u64{self.kind.apk_bytes()}
    pub(crate) fn apk_sha256(&self)->&'static str{self.kind.apk_sha256()}
    pub(crate) fn certificate_sha256(&self)->&'static str{self.kind.certificate_sha256()}
    pub(crate) fn guard(&self,end:Instant)->io::Result<()>{
        if end>self.end{return Err(bad("fixture material deadline cannot be renewed"));}
        before(end)?;
        self.held.guard(end)?;
        before(end)
    }
    pub(crate) fn apk_file(&self,end:Instant)->io::Result<&File>{
        self.guard(end)?;
        self.held.apk_file(end)
    }
    pub(crate) fn comparison(&self)->Value{
        let material=self.held.comparison();
        json!({"schema":"droidloom.native-leaf-fixture-material.v2","kind":self.kind,
            "package":self.package(),"run_id":self.run_id(),"version_code":self.version_code(),
            "apk_bytes":self.apk_bytes(),"apk_sha256":self.apk_sha256(),
            "certificate_sha256":self.certificate_sha256(),"material":material,
            "guest_staging_used":false,"installation_authority":false})
    }
}

#[cfg(test)]
mod tests{
    use super::*;
    #[test]
    fn native_leaf_fixture_material_has_only_six_original_routes_and_four_fixed_materials(){
        use NativeLeafApkRoute as R;
        let positive=[(R::DocumentsSaf,NativeLeafFixtureKind::DocumentsSaf),
            (R::DocumentsSearch,NativeLeafFixtureKind::DocumentsFeatures),
            (R::GalleryRotation,NativeLeafFixtureKind::GalleryRotation),
            (R::GalleryVideo,NativeLeafFixtureKind::GalleryVideo),
            (R::GallerySeek,NativeLeafFixtureKind::GalleryVideo),
            (R::GalleryAlbum,NativeLeafFixtureKind::GalleryVideo)];
        for (route,kind) in positive{
            assert_eq!(NativeLeafFixtureKind::for_route(route).unwrap(),kind);
            assert_ne!(route.package(),kind.package());
            assert!(kind.apk_bytes()>0 && kind.apk_bytes()<262144);
            assert_eq!(kind.version_code(),1);
            assert_eq!(kind.apk_sha256().len(),64);
            assert_eq!(kind.certificate_sha256().len(),64);
            let members=crate::prebuilt_native_helpers::MEMBERS;
            let apk=members.iter().find(|m|m.kind==kind.normal_kind() && m.relative=="helper.apk").unwrap();
            assert_eq!((apk.bytes,apk.sha256),(kind.apk_bytes(),kind.apk_sha256()));
            let cert=members.iter().find(|m|m.kind==kind.normal_kind() && m.relative=="signer.der").unwrap();
            assert_eq!(cert.sha256,kind.certificate_sha256());
            assert!(apk.embedded_body().unwrap().is_none());
            assert!(cert.embedded_body().unwrap().is_none());
        }
        for route in [R::CalendarCore,R::CalendarReminder,R::CameraPhoto,R::ContactsSearch,
            R::ClockPair,R::ClockAlarm,R::SettingsSupportedPages,R::IhgLondon]{
            assert!(NativeLeafFixtureKind::for_route(route).is_err());
        }
        for raw in [r#""caller""#,r#"{"gallery_video":{"package":"com.android.settings"}}"#]{
            assert!(serde_json::from_str::<NativeLeafFixtureKind>(raw).is_err());
        }
    }
}
