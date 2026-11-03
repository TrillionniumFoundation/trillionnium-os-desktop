// SPDX-License-Identifier: MPL-2.0

mod arg_budget;
pub(super) mod elf;
mod shebang;

pub(in crate::process) use self::arg_budget::ArgBudget;
use self::{
    elf::{ElfHeaders, ElfLoadInfo, load_elf_to_vmar},
    shebang::parse_shebang_line,
};
use crate::{
    fs::{
        file::{AccessMode, FileLike, InodeHandle, InodeType, Permission, StatusFlags},
        vfs::{
            inode::Inode,
            notify,
            path::{FsPath, Path, PathResolver},
        },
    },
    prelude::*,
    vm::vmar::Vmar,
};

/// An opened executable whose format has not yet been detected.
///
/// The file has already passed executable-file permission and type checks,
/// but it is not yet known to be an ELF image or a shebang script.
/// It also retains the path-access information needed if detection identifies a script.
pub(crate) struct UndetectedExecutable {
    file: Arc<dyn FileLike>,
    script_path: ShebangScriptPath,
}

impl UndetectedExecutable {
    #[cfg(feature = "g1d-trusted-control")]
    pub(in crate::process) fn snapshot_trusted_initial(
        self,
    ) -> Result<elf::TrustedInitialSnapshot> {
        elf::TrustedInitialSnapshot::read(self.file)
    }

    /// The experimental initial loader consumes the opened input directly.
    /// Ordinary exec and shebang resolution never call this entry point.
    #[cfg(feature = "g1c-trusted-observe")]
    pub(in crate::process) fn load_trusted_initial(
        self,
        vmar: Arc<Vmar>,
        argv: Vec<CString>,
        envp: Vec<CString>,
    ) -> Result<(ElfLoadInfo, elf::LoadedInitialImage)> {
        elf::load_trusted_initial(self.file, vmar, argv, envp)
    }

    /// Opens an executable without detecting its format.
    ///
    /// `script_path` describes whether a shebang interpreter can reopen this file after exec.
    pub(crate) fn open(path: Path, script_path: ShebangScriptPath) -> Result<Self> {
        let file = open_executable_file(path)?;
        Ok(Self { file, script_path })
    }

    /// Returns the path of the opened executable.
    pub(crate) fn path(&self) -> &Path {
        self.file.path()
    }

    /// Consumes this executable and classifies it as an ELF image or a shebang script.
    fn detect_format(self) -> Result<DetectedExecutable> {
        let mut first_page = Box::new([0u8; PAGE_SIZE]);
        let len = self.file.read_bytes_at(0, &mut *first_page)?;

        let Some(interpreter_argv) = parse_shebang_line(&first_page[..len])? else {
            let headers = ElfHeaders::parse(&first_page[..len])?;
            return Ok(DetectedExecutable::Elf {
                file: self.file,
                headers,
            });
        };

        // A shebang interpreter must reopen the original script path after exec. A path
        // synthesized from a close-on-exec file descriptor will no longer be accessible then,
        // so fail before changing the process state.
        // Reference: <https://elixir.bootlin.com/linux/v6.8/source/fs/binfmt_script.c#L93>
        let script_path = match self.script_path {
            ShebangScriptPath::Accessible(path) => path,
            ShebangScriptPath::Inaccessible => {
                return_errno_with_message!(
                    Errno::ENOENT,
                    "the script path is inaccessible after closing close-on-exec file descriptors"
                );
            }
        };

        Ok(DetectedExecutable::Script {
            interpreter_argv,
            script_path,
        })
    }
}

/// An executable classified as an ELF image or a shebang script.
///
/// Each variant contains the validated metadata required by the next loading step.
/// An ELF image retains its opened file and parsed headers,
/// while a script retains its interpreter arguments and the path passed to that interpreter.
enum DetectedExecutable {
    Elf {
        file: Arc<dyn FileLike>,
        headers: ElfHeaders,
    },
    Script {
        interpreter_argv: Vec<CString>,
        script_path: CString,
    },
}

/// Opens a path as an executable file.
fn open_executable_file(path: Path) -> Result<Arc<dyn FileLike>> {
    check_executable_inode(path.inode().as_ref())?;

    let file: Arc<dyn FileLike> = Arc::new(InodeHandle::new_unchecked_access(
        path,
        // Reference: <https://elixir.bootlin.com/linux/v7.0/source/fs/exec.c#L769>.
        AccessMode::O_RDONLY,
        StatusFlags::empty(),
    )?);
    notify::on_open(file.common());

    Ok(file)
}

/// Describes how a shebang interpreter can access the script after exec.
pub(crate) enum ShebangScriptPath {
    /// A path accessible to the interpreter after exec.
    Accessible(CString),
    /// A path inaccessible to the interpreter after exec.
    Inaccessible,
}

/// Represents an executable file that is ready to be loaded into memory and executed.
///
/// This struct encapsulates the ELF file to be executed along with its header data,
/// the `argv` and the `envp` which is required for the program execution.
pub(super) struct ProgramToLoad {
    elf_file: Arc<dyn FileLike>,
    elf_headers: ElfHeaders,
    dumpable: bool,
    argv: Vec<CString>,
    envp: Vec<CString>,
}

impl ProgramToLoad {
    /// Constructs a new `ProgramToLoad` from an opened executable and handles shebang
    /// interpretation if necessary.
    pub(super) fn from_executable(
        mut executable: UndetectedExecutable,
        path_resolver: &PathResolver,
        mut argv: Vec<CString>,
        envp: Vec<CString>,
        stack_limit_bytes: u64,
    ) -> Result<Self> {
        ArgBudget::for_args(stack_limit_bytes, &argv, &envp)?;
        // A limit to the recursion depth of shebang executables.
        //
        // If the interpreter is a shebang, then recursion will be triggered. If it loops, we
        // should fail. We follow the same limit as Linux.
        let mut recursive_limit = 5;

        let mut dumpable = true;
        let (elf_file, elf_headers) = loop {
            dumpable &= executable
                .path()
                .inode()
                .check_permission(Permission::MAY_READ)
                .is_ok();
            let (mut new_argv, current_script_path) = match executable.detect_format()? {
                DetectedExecutable::Elf { file, headers } => break (file, headers),
                DetectedExecutable::Script {
                    interpreter_argv,
                    script_path,
                } => (interpreter_argv, script_path),
            };

            if recursive_limit == 0 {
                return_errno_with_message!(Errno::ELOOP, "the recursive limit is reached");
            }
            recursive_limit -= 1;

            // Count the actual replacement before allocating the concatenated
            // vector. The discarded argv[0] no longer consumes the budget;
            // interpreter arguments and the script path do consume it.
            let mut rewritten_budget = ArgBudget::new(stack_limit_bytes);
            rewritten_budget.charge_strings(
                new_argv
                    .iter()
                    .chain(core::iter::once(&current_script_path))
                    .chain(argv.iter().skip(1))
                    .chain(&envp),
            )?;
            new_argv.try_reserve(argv.len().max(1)).map_err(|_| {
                Error::with_message(
                    Errno::ENOMEM,
                    "cannot allocate the interpreter argument vector",
                )
            })?;

            let interpreter_filename = new_argv[0].clone();
            let interpreter = {
                let filename = interpreter_filename.to_str()?;
                let fs_path = FsPath::try_from(filename)?;
                path_resolver.lookup(&fs_path)?
            };

            // Update the argument list and the executable inode. Then, try again.
            //
            // The interpreter receives the script path as its first argument,
            // regardless of the caller-supplied `argv[0]`. For example,
            // `exec -a custom ./script arg` with `#!/bin/sh` must execute
            // `/bin/sh ./script arg`, not `/bin/sh custom arg`.
            new_argv.push(current_script_path);
            new_argv.extend(argv.into_iter().skip(1));
            argv = new_argv;
            executable = UndetectedExecutable::open(
                interpreter,
                ShebangScriptPath::Accessible(interpreter_filename),
            )?;
        };

        Ok(Self {
            elf_file,
            elf_headers,
            dumpable,
            argv,
            envp,
        })
    }

    /// Returns the `Path` of the ELF file that will be loaded.
    pub(super) fn elf_path(&self) -> &Path {
        self.elf_file.path()
    }

    /// Loads the executable into the specified virtual memory space.
    ///
    /// Returns the information about the ELF loading process.
    pub(super) fn load_to_vmar(
        self,
        vmar: &Vmar,
        path_resolver: &PathResolver,
    ) -> Result<ElfLoadInfo> {
        if !self.dumpable {
            *vmar.process_vm().dumpable().lock() = false;
        }
        load_elf_to_vmar(
            vmar,
            self.elf_file,
            path_resolver,
            self.elf_headers,
            self.argv,
            self.envp,
        )
    }
}

fn check_executable_inode(inode: &dyn Inode) -> Result<()> {
    if inode.type_().is_directory() {
        return_errno_with_message!(Errno::EISDIR, "the inode is a directory");
    }

    if inode.type_() == InodeType::SymLink {
        return_errno_with_message!(Errno::ELOOP, "the inode is a symbolic link");
    }

    if !inode.type_().is_regular_file() {
        return_errno_with_message!(Errno::EACCES, "the inode is not a regular file");
    }

    if inode.check_permission(Permission::MAY_EXEC).is_err() {
        return_errno_with_message!(Errno::EACCES, "the inode is not executable");
    }

    Ok(())
}
