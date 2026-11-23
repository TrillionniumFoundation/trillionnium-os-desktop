//! Four private launch command shapes. These select the held cmd executable;
//! the wire never contains an executable, namespace, descriptor or MAC label.
use super::*;
use droidloom_task_launcher::LaunchRequest;
use droidloom_task_launcher::effects::AndroidCommand;

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(crate) struct LaunchInputs {
    package: String,
    component: Option<String>,
    user: u32,
    resolution: Option<(u32, u32)>,
}

impl LaunchInputs {
    fn of(request: &LaunchRequest) -> Result<Self> {
        require(
            package_valid(&request.package) && request.user <= 21_474,
            "launch user exceeds the owned Android mapping",
        )?;
        // Use the already reviewed closed intent validation, including the
        // component/package relationship and protocol record bounds.
        AndroidCommand::Start {
            request: request.clone(),
        }
        .arguments()
        .map_err(external)?;
        Ok(Self {
            package: request.package.clone(),
            component: request.component.clone(),
            user: request.user,
            resolution: request.resolution,
        })
    }

    fn request(&self) -> Result<LaunchRequest> {
        let request = LaunchRequest {
            package: self.package.clone(),
            component: self.component.clone(),
            user: self.user,
            resolution: self.resolution,
        };
        require(
            Self::of(&request)? == *self,
            "noncanonical closed launch inputs",
        )?;
        Ok(request)
    }
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(tag = "launch", deny_unknown_fields)]
pub(crate) enum LaunchCommand {
    ListTasks {},
    ResolvePermissionDialog { user: u32 },
    Start { inputs: LaunchInputs },
    ResolveAlias { inputs: LaunchInputs },
}

impl LaunchCommand {
    pub(super) fn bind(command: &AndroidCommand, bound: &LaunchRequest) -> Result<Self> {
        let inputs = LaunchInputs::of(bound)?;
        let value = match command {
            AndroidCommand::ListTasks => Self::ListTasks {},
            AndroidCommand::ResolvePermissionDialog { user } => {
                require(
                    *user == bound.user,
                    "launch permission resolver user changed",
                )?;
                Self::ResolvePermissionDialog { user: *user }
            }
            AndroidCommand::Start { request } => {
                require(
                    *request == *bound,
                    "launch start differs from its bound request",
                )?;
                Self::Start { inputs }
            }
            AndroidCommand::ResolveAlias { request } => {
                require(
                    *request == *bound,
                    "launch alias differs from its bound request",
                )?;
                Self::ResolveAlias { inputs }
            }
        };
        value.validate()?;
        Ok(value)
    }

    fn command(&self) -> Result<AndroidCommand> {
        Ok(match self {
            Self::ListTasks {} => AndroidCommand::ListTasks,
            Self::ResolvePermissionDialog { user } => {
                require(
                    *user <= 21_474,
                    "launch permission user exceeds the owned mapping",
                )?;
                AndroidCommand::ResolvePermissionDialog { user: *user }
            }
            Self::Start { inputs } => AndroidCommand::Start {
                request: inputs.request()?,
            },
            Self::ResolveAlias { inputs } => AndroidCommand::ResolveAlias {
                request: inputs.request()?,
            },
        })
    }

    pub(super) fn validate(&self) -> Result<()> {
        self.command()?.arguments().map_err(external).map(|_| ())
    }

    pub(super) fn arguments(&self) -> Result<Vec<CString>> {
        let mut arguments = vec![CString::new("/system/bin/cmd").unwrap()];
        for argument in self.command()?.arguments().map_err(external)? {
            arguments.push(CString::new(argument).map_err(external)?);
        }
        Ok(arguments)
    }

    pub(super) const fn domain(&self) -> OperationDomain {
        match self {
            Self::Start { .. } => OperationDomain::LaunchStart,
            Self::ListTasks {}
            | Self::ResolvePermissionDialog { .. }
            | Self::ResolveAlias { .. } => OperationDomain::LaunchRead,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn request() -> LaunchRequest {
        LaunchRequest {
            package: "org.example.app".into(),
            component: None,
            user: 10,
            resolution: None,
        }
    }

    #[test]
    fn launch_commands_bind_four_shapes_to_one_user_package_and_fixed_cmd_role() {
        let bound = request();
        for command in [
            AndroidCommand::ListTasks,
            AndroidCommand::ResolvePermissionDialog { user: 10 },
            AndroidCommand::Start {
                request: bound.clone(),
            },
            AndroidCommand::ResolveAlias {
                request: bound.clone(),
            },
        ] {
            let closed = LaunchCommand::bind(&command, &bound).unwrap();
            let operation = ApplicationOperation::Launch {
                value: closed.clone(),
            };
            assert_eq!(operation.binary(), c"cmd");
            assert_eq!(operation.descriptor_count(), 15);
            assert!(!operation.needs_content_jar());
            assert_eq!(
                closed
                    .arguments()
                    .unwrap()
                    .iter()
                    .map(|s| s.to_str().unwrap())
                    .collect::<Vec<_>>(),
                std::iter::once("/system/bin/cmd")
                    .chain(command.arguments().unwrap().iter().map(String::as_str))
                    .collect::<Vec<_>>()
            );
            assert_ne!(operation.domain(), OperationDomain::Browser);
            assert_ne!(operation.domain(), OperationDomain::Query);
            assert_eq!(
                serde_json::from_slice::<LaunchCommand>(&serde_json::to_vec(&closed).unwrap())
                    .unwrap(),
                closed
            );
        }
        let mut changed = bound.clone();
        changed.package = "org.other.app".into();
        assert!(LaunchCommand::bind(&AndroidCommand::Start { request: changed }, &bound).is_err());
        assert!(
            LaunchCommand::bind(&AndroidCommand::ResolvePermissionDialog { user: 0 }, &bound)
                .is_err()
        );
        let mut changed = bound.clone();
        changed.component = Some("org.other.app/.Main".into());
        assert!(LaunchInputs::of(&changed).is_err());
        let mut changed = bound;
        changed.user = 21_475;
        assert!(LaunchInputs::of(&changed).is_err());
    }

    #[test]
    fn launch_wire_rejects_authority_fields_and_unknown_operations() {
        for body in [
            r#"{"launch":"ListTasks","pid":123}"#,
            r#"{"launch":"ListTasks","argv":["sh"]}"#,
            r#"{"launch":"ResolvePermissionDialog","user":0,"domain":"u:r:shell:s0"}"#,
            r#"{"launch":"Start","inputs":{"package":"org.example.app","component":null,"user":0,"resolution":null,"namespace":7}}"#,
            r#"{"launch":"Connect","socket":"/dev/socket/other"}"#,
        ] {
            assert!(
                serde_json::from_str::<LaunchCommand>(body).is_err(),
                "{body}"
            );
        }
        assert_ne!(
            OperationDomain::LaunchRead.context(),
            OperationDomain::LaunchStart.context()
        );
    }
}
