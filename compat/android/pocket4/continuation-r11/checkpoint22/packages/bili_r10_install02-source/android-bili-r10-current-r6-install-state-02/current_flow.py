"""Explicit owned Flow subtype; one discovery argument differs from frozen R6.

No recorder module, method, app module, QA Session or transport is patched.
The constructor, scope, guards, command, action lock, launch and cleanup bodies
remain inherited from the exact R6 recorder. Only this bind method passes the
current discovery facade as MainBinding's existing app parameter.
"""

R6_MANIFEST = "002ee581a4bb399536dd7d594d01f050e2540d9c049b0cfb37e1c96954b6caff"
MAIN_EPOCH = "7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c"
BASELINE_SHA = "633912ff4595ce898c4c0e0f9ac06c1f422203d90fbd2e583192f35ff7a04364"
QUALIFICATION_SHA = "ae8d54ee64fe23676d7f68f8092c0915d3f0f41662d8b7d4be86b85201071a6e"


def flow_type(recorder, discovery):
    recorder.require(discovery.BASELINE_SHA == BASELINE_SHA and
        discovery.QUALIFICATION_SHA == QUALIFICATION_SHA and
        discovery.MAIN_EPOCH == MAIN_EPOCH,
        "CURRENT_DISCOVERY_FACTORY_BINDING_REQUIRED")
    require = recorder.require
    write_new = recorder.write_new
    subprocess = recorder.subprocess
    class CurrentFlow(recorder.Flow):
        def bind(self):
            if self.binding is not None:
                return self.binding
            module = self.contract.load('main_binding.py', 'bili_main_binding')
            binding = module.MainBinding(contract=self.contract, source=self.source, scope=self.scope,
                activation=self.activation, epoch=self.epoch,
                app=discovery.discovery_view(self.app,self.activation,self.epoch,lambda:self.guard()),
                guard=lambda: self.guard())
            try:
                write_new(self.step / 'held-main-binding.json', binding.record)
            except BaseException as original:
                try:
                    binding.close()
                except BaseException as secondary:
                    original.add_note('held binding close: ' + type(secondary).__name__)
                raise
            self.binding = binding
            def record(kind, value):
                write_new(self.step / ('transport-%03d.%s.json' % (value['sequence'], kind)), value)
            def runner(argv, **options):
                require(options['close_fds'] is True and options['stdout'] == subprocess.PIPE and
                        options['stderr'] == subprocess.PIPE, 'HELD_RUNNER_IO_PROTOCOL_CHANGED')
                if self._private_backend_transport:
                    # The existing backend crops a screencap in memory before it
                    # emits the scoped observation. Do not persist its unscoped
                    # frame or intermediate native tree as a new raw log.
                    self.action_attempted |= self._android_mutation
                    return subprocess.run(argv, **options)
                return self.command(argv, options['timeout'], mutation=self._android_mutation,
                    label='Android command', pass_fds=options['pass_fds'], check=False,
                    host_env=options['env'])
            self.transport = binding.transport(record=record, runner=runner,
                guard=lambda action_attempted: self.guard(attempted=self.action_attempted))
            return binding


    return CurrentFlow
