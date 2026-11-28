//! Fixed selected-proc loans for authenticated Android observation helpers.
//! A source borrows the same early board's acquired MAC object and selection.
//! Only a single PIDFD-derived process directory crosses a helper channel; the
//! detached mount/root and the original policy owner never leave the broker.
use super::*;
use crate::production_application::{EngineTarget, MetadataRole};

pub(crate) struct ObserverProcSource<'a> {
    mac: &'a MacPreflight,
    selection: &'a ProductionSelection,
}
pub(crate) struct ObserverProcTarget<'a> {
    source: ObserverProcSource<'a>,
    held: host_proc::ObserverTarget,
    end: Instant,
}

impl MacPreflight {
    pub(crate) fn observer_proc<'a>(
        &'a self,
        selection: &'a ProductionSelection,
    ) -> Result<ObserverProcSource<'a>> {
        let value = ObserverProcSource {
            mac: self,
            selection,
        };
        value.revalidate()?;
        Ok(value)
    }
}
impl ObserverProcSource<'_> {
    pub(crate) fn revalidate(&self) -> Result<()> {
        self.mac.revalidate(self.selection)?;
        require(
            self.selection.is_kernel_first() && self.mac.scoped_contexts(),
            "Android observer requires its original selected host proc provider",
        )
    }
    fn issue<'a>(
        &'a self,
        target: &File,
        factory: Option<&File>,
        end: Instant,
    ) -> Result<ObserverProcTarget<'a>> {
        require(Instant::now() < end, "selected observer original deadline")?;
        self.revalidate()?;
        let view = self
            .mac
            .host_proc
            .as_ref()
            .ok_or(MacError::Rejected("selected observer provider absent"))?;
        let held = view.for_observer(&self.mac.loaded, self.selection, target, factory)?;
        let value = ObserverProcTarget {
            source: ObserverProcSource {
                mac: self.mac,
                selection: self.selection,
            },
            held,
            end,
        };
        value.revalidate()?;
        Ok(value)
    }
    pub(crate) fn metadata<'a>(
        &'a self,
        role: MetadataRole,
        target: &File,
        end: Instant,
    ) -> Result<ObserverProcTarget<'a>> {
        require(
            role != MetadataRole::CalendarCounts,
            "Calendar uses only its original high factory metadata route",
        )?;
        self.issue(target, None, end)
    }
    pub(crate) fn engine<'a>(
        &'a self,
        request: &EngineTarget,
        target: &File,
        end: Instant,
    ) -> Result<ObserverProcTarget<'a>> {
        require(
            crate::engine_custody::selected_package(&request.package)
                && crate::engine_custody::user_zero_app_uid(request.uid),
            "selected engine observer package or user-zero UID differs",
        )?;
        self.issue(target, None, end)
    }
    pub(crate) fn calendar<'a>(
        &'a self,
        target: &File,
        factory: &File,
        end: Instant,
    ) -> Result<ObserverProcTarget<'a>> {
        // Only the authenticated factory's original Born PIDFD can reach this
        // fixed route. The high observer reads labels after actual TRACEEXEC.
        self.issue(target, Some(factory), end)
    }
}
impl ObserverProcTarget<'_> {
    pub(crate) fn directory(&self) -> &File {
        self.held.directory()
    }
    pub(crate) fn revalidate(&self) -> Result<()> {
        require(
            Instant::now() < self.end,
            "selected observer original deadline",
        )?;
        self.source.revalidate()?;
        let view = self
            .source
            .mac
            .host_proc
            .as_ref()
            .ok_or(MacError::Rejected("selected observer provider disappeared"))?;
        view.revalidate_observer(&self.source.mac.loaded, self.source.selection, &self.held)?;
        require(
            Instant::now() < self.end,
            "selected observer original deadline",
        )
    }
}
