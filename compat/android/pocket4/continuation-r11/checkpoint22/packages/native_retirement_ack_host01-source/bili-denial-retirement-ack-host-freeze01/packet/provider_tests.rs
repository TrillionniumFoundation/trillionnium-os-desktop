
#[cfg(test)]
mod retirement_provider_tests {
    use super::*;
    use std::sync::atomic::Ordering::SeqCst;
    use droidloom_denial_ipc::SeqPacket;
    use droidloom_denial_protocol::{AndroidDisplayId, Transform};
    use droidloom_transport::{Damage, FormatModifier, FrameId, PlaneMetadata};
    use droidloom_composer::{Composition, LayerId, LayerState, PowerMode, TaskWindowSpec};

    const DISPLAY: DisplayId = DisplayId(9);
    const OBJECT: TaskObjectId = TaskObjectId(7);

    fn reservation(display: DisplayId) -> ReservedTaskWindowSpec {
        ReservedTaskWindowSpec { display, package: "org.example.retirement".to_owned() }
    }
    fn pair() -> (DenialPresentationSink, ProtocolSocket, crate::SyncobjDevice) {
        let (a,b) = SeqPacket::pair().unwrap();
        a.set_nonblocking(true).unwrap();
        b.set_nonblocking(true).unwrap();
        let device = crate::SyncobjDevice::fixture();
        (DenialPresentationSink::new(ProtocolSocket::new(a),device.clone())
            .with_retirement_receipts(true).with_activation_requests(true),
         ProtocolSocket::new(b),device)
    }
    fn wire(peer: &ProtocolSocket) -> AndroidMessage {
        let deadline = Instant::now()+Duration::from_secs(1);
        loop {
            match peer.receive_android() {
                Ok(value) => return value.message,
                Err(IpcError::Io(error)) if error.kind()==std::io::ErrorKind::WouldBlock => {
                    assert!(Instant::now()<deadline,"expected source method did not send");
                    std::thread::yield_now();
                }
                other => panic!("wire receive: {other:?}"),
            }
        }
    }
    fn no_wire(peer: &ProtocolSocket) {
        assert!(matches!(peer.receive_android(),
            Err(IpcError::Io(error)) if error.kind()==std::io::ErrorKind::WouldBlock));
    }
    fn register(sink: &DenialPresentationSink, peer: &ProtocolSocket, display: DisplayId, object: TaskObjectId) {
        sink.register_task(object,&reservation(display)).unwrap();
        assert_eq!(wire(peer),AndroidMessage::CreateTask {
            object,display:AndroidDisplayId(display.0),package:"org.example.retirement".to_owned(),
        });
        assert_eq!(wire(peer),AndroidMessage::BindTimelines {object});
        assert!(sink.lock_tasks().unwrap().get(&display).unwrap().registration_complete);
        no_wire(peer);
    }
    fn start_retirement(sink: &DenialPresentationSink, peer: &ProtocolSocket,
                        display: DisplayId, object: TaskObjectId)
                        -> (std::thread::JoinHandle<Result<(),DenialSinkError>>,RetirementNonce) {
        let owned=sink.clone();
        let child=std::thread::spawn(move||owned.unregister_task(display,object));
        let AndroidMessage::RetireTask{object:actual,nonce}=wire(peer) else {panic!("missing RetireTask")};
        assert_eq!(actual,object);
        assert_ne!(nonce.0,0);
        (child,nonce)
    }
    fn receive_ack(sink:&DenialPresentationSink,peer:&ProtocolSocket,object:TaskObjectId,nonce:RetirementNonce)
                   -> Result<(),DenialSinkError> {
        peer.send_denial(&DenialMessage::TaskRetired{object,nonce}).unwrap();
        let deadline=Instant::now()+Duration::from_secs(1);
        loop {
            match sink.socket().receive_denial() {
                Ok(value) => {
                    let DenialMessage::TaskRetired{object,nonce}=value.message else{panic!("wrong record")};
                    return sink.accept_retirement_receipt(sink.socket(),object,nonce);
                }
                Err(IpcError::Io(error)) if error.kind()==std::io::ErrorKind::WouldBlock=>{
                    assert!(Instant::now()<deadline); std::thread::yield_now();
                }
                other=>panic!("ack receive: {other:?}"),
            }
        }
    }
    fn metadata(id:u64)->BufferMetadata {
        BufferMetadata{id:BufferId(id),width:800,height:600,
            format:FormatModifier{fourcc:u32::from_le_bytes(*b"XR24"),modifier:0},
            planes:vec![PlaneMetadata{index:0,offset:0,stride:3200}]}
    }
    fn target(id:u64,reserved:bool,busy:bool)->HostRenderTarget {
        HostRenderTarget{configure_serial:5,metadata:metadata(id),
            plane_fds:vec![std::fs::File::open("/dev/null").unwrap().into()],
            reserved,busy,revoked:false}
    }

    #[test]
    fn duplicate_display_cannot_destroy_another_real_provider_owner() {
        let(sink,peer,device)=pair();
        register(&sink,&peer,DISPLAY,OBJECT);
        let creates=device.seam.creates.load(SeqCst);
        assert!(matches!(sink.register_task(TaskObjectId(8),&reservation(DISPLAY)),
            Err(DenialSinkError::DuplicateDisplay(DISPLAY))));
        assert!(matches!(sink.unregister_task(DISPLAY,TaskObjectId(8)),
            Err(DenialSinkError::OwnershipMismatch{display:DISPLAY,expected:TaskObjectId(8),actual:OBJECT})));
        let tasks=sink.lock_tasks().unwrap();
        let old=tasks.get(&DISPLAY).unwrap();
        assert_eq!(old.binding.object(),OBJECT);
        assert!(old.registration_complete&&old.retirement.is_none());
        assert!(tasks.preparations.is_empty());
        assert_eq!(device.seam.creates.load(SeqCst),creates);
        drop(tasks);
        no_wire(&peer);
    }

    #[test]
    fn duplicate_object_on_another_display_has_no_claim_or_remote_effect() {
        let(sink,peer,device)=pair();
        register(&sink,&peer,DISPLAY,OBJECT);
        assert!(matches!(sink.register_task(OBJECT,&reservation(DisplayId(10))),
            Err(DenialSinkError::DuplicateObject(OBJECT))));
        assert_eq!(device.seam.creates.load(SeqCst),1);
        assert!(!sink.lock_tasks().unwrap().contains_key(&DisplayId(10)));
        assert!(sink.lock_tasks().unwrap().preparations.is_empty());
        no_wire(&peer);
    }

    #[test]
    fn local_timeline_creation_failure_has_exact_no_send_cleanup_proof() {
        let(sink,peer,device)=pair();
        device.seam.fail_create.store(true,SeqCst);
        assert!(matches!(sink.register_task(OBJECT,&reservation(DISPLAY)),Err(DenialSinkError::Syncobj(_))));
        {
            let tasks=sink.lock_tasks().unwrap();
            assert!(!tasks.contains_key(&DISPLAY));
            let entry=tasks.preparations.get(&DISPLAY).unwrap();
            assert_eq!(entry.object,OBJECT);
            assert!(entry.primary_error.as_ref().unwrap().contains("fixture-create-failure"));
        }
        assert!(matches!(sink.unregister_task(DISPLAY,TaskObjectId(8)),Err(DenialSinkError::OwnershipMismatch{..})));
        assert!(sink.lock_tasks().unwrap().preparations.contains_key(&DISPLAY));
        sink.unregister_task(DISPLAY,OBJECT).unwrap();
        assert!(sink.lock_tasks().unwrap().preparations.is_empty());
        no_wire(&peer);
    }

    #[test]
    fn local_descriptor_export_failure_retains_primary_until_exact_cleanup() {
        let(sink,peer,device)=pair();
        device.seam.fail_export.store(true,SeqCst);
        assert!(matches!(sink.register_task(OBJECT,&reservation(DISPLAY)),Err(DenialSinkError::Syncobj(_))));
        assert_eq!(device.seam.creates.load(SeqCst),1);
        assert_eq!(device.seam.exports.load(SeqCst),1);
        assert!(sink.lock_tasks().unwrap().preparations.get(&DISPLAY).unwrap()
            .primary_error.as_ref().unwrap().contains("fixture-export-failure"));
        sink.unregister_task(DISPLAY,OBJECT).unwrap();
        no_wire(&peer);
    }

    #[test]
    fn create_send_failure_does_not_erase_the_potential_remote_owner() {
        let(sink,peer,_)=pair(); drop(peer);
        assert!(matches!(sink.register_task(OBJECT,&reservation(DISPLAY)),Err(DenialSinkError::Ipc(_))));
        let tasks=sink.lock_tasks().unwrap();
        let task=tasks.get(&DISPLAY).unwrap();
        assert!(task.create_attempted&&!task.create_sent&&!task.timelines_attempted);
        assert!(!task.registration_complete&&task.primary_registration_error.is_some());
        assert!(tasks.preparations.is_empty());
    }

    #[test]
    fn bind_timelines_send_failure_retains_partial_state_without_legacy_destroy() {
        let(sink,peer,device)=pair();
        *device.seam.close_peer_on_descriptor_borrow.lock().unwrap()=Some(peer);
        assert!(matches!(sink.register_task(OBJECT,&reservation(DISPLAY)),Err(DenialSinkError::Ipc(_))));
        let tasks=sink.lock_tasks().unwrap();
        let task=tasks.get(&DISPLAY).unwrap();
        assert!(task.create_attempted&&task.create_sent&&task.timelines_attempted);
        assert!(!task.registration_complete&&task.primary_registration_error.is_some());
        assert!(task.retirement.is_none());
    }

    #[test]
    fn retirement_waits_for_the_same_socket_object_and_nonce_receipt() {
        let(sink,peer,_)=pair();register(&sink,&peer,DISPLAY,OBJECT);
        let(child,nonce)=start_retirement(&sink,&peer,DISPLAY,OBJECT);
        assert!(!child.is_finished());
        assert!(sink.lock_tasks().unwrap().contains_key(&DISPLAY));
        receive_ack(&sink,&peer,OBJECT,nonce).unwrap();
        child.join().unwrap().unwrap();
        assert!(!sink.lock_tasks().unwrap().contains_key(&DISPLAY));
        no_wire(&peer);
    }

    #[test]
    fn old_peer_cannot_enter_registration_or_gain_a_legacy_destroy_fallback() {
        let(sink,peer,device)=pair();
        let sink=sink.with_retirement_receipts(false);
        assert!(matches!(sink.register_task(OBJECT,&reservation(DISPLAY)),Err(DenialSinkError::RetirementUnsupported)));
        assert_eq!(device.seam.creates.load(SeqCst),0);
        assert!(sink.lock_tasks().unwrap().is_empty());
        no_wire(&peer);
    }

    #[test]
    fn wrong_receipt_object_or_nonce_cannot_complete_the_pending_owner() {
        let(sink,peer,_)=pair();register(&sink,&peer,DISPLAY,OBJECT);
        let(child,nonce)=start_retirement(&sink,&peer,DISPLAY,OBJECT);
        assert!(matches!(receive_ack(&sink,&peer,TaskObjectId(8),nonce),Err(DenialSinkError::UnknownObject(_))));
        assert!(matches!(receive_ack(&sink,&peer,OBJECT,RetirementNonce(nonce.0+1)),Err(DenialSinkError::RetirementMismatch{..})));
        assert!(!sink.lock_tasks().unwrap().get(&DISPLAY).unwrap().retirement.as_ref().unwrap().receipt_received);
        receive_ack(&sink,&peer,OBJECT,nonce).unwrap();
        child.join().unwrap().unwrap();
    }

    #[test]
    fn foreign_socket_instance_is_rejected_before_pending_state_changes() {
        let(sink,peer,_)=pair();register(&sink,&peer,DISPLAY,OBJECT);
        let(child,nonce)=start_retirement(&sink,&peer,DISPLAY,OBJECT);
        let(a,_b)=SeqPacket::pair().unwrap();let foreign=ProtocolSocket::new(a);
        assert!(matches!(sink.accept_retirement_receipt(&foreign,OBJECT,nonce),Err(DenialSinkError::RetirementForeignPeer)));
        assert!(!sink.lock_tasks().unwrap().get(&DISPLAY).unwrap().retirement.as_ref().unwrap().receipt_received);
        receive_ack(&sink,&peer,OBJECT,nonce).unwrap();
        child.join().unwrap().unwrap();
    }

    #[test]
    fn unrequested_receipt_cannot_retire_a_live_channel() {
        let(sink,peer,_)=pair();register(&sink,&peer,DISPLAY,OBJECT);
        assert!(matches!(receive_ack(&sink,&peer,OBJECT,RetirementNonce(1)),Err(DenialSinkError::RetirementMismatch{..})));
        assert!(sink.lock_tasks().unwrap().get(&DISPLAY).unwrap().retirement.is_none());
        no_wire(&peer);
    }

    #[test]
    fn nonce_exhaustion_does_not_wrap_or_send_a_replayed_request() {
        let(sink,peer,_)=pair();register(&sink,&peer,DISPLAY,OBJECT);
        sink.lock_tasks().unwrap().next_nonce=u64::MAX;
        assert!(matches!(sink.unregister_task(DISPLAY,OBJECT),Err(DenialSinkError::RetirementNonceExhausted)));
        assert!(sink.lock_tasks().unwrap().get(&DISPLAY).unwrap().retirement.is_none());
        no_wire(&peer);
    }

    #[test]
    fn timeout_retains_resources_and_late_ack_finishes_without_resending() {
        let(sink,peer,_)=pair();register(&sink,&peer,DISPLAY,OBJECT);
        let result=sink.unregister_task(DISPLAY,OBJECT);
        let Err(DenialSinkError::RetirementPending{object,nonce})=result else{panic!("expected bounded pending")};
        assert_eq!(object,OBJECT);
        assert_eq!(wire(&peer),AndroidMessage::RetireTask{object,nonce});
        assert!(sink.lock_tasks().unwrap().contains_key(&DISPLAY));
        receive_ack(&sink,&peer,OBJECT,nonce).unwrap();
        sink.unregister_task(DISPLAY,OBJECT).unwrap();
        assert!(!sink.lock_tasks().unwrap().contains_key(&DISPLAY));
        no_wire(&peer);
    }

    #[test]
    fn disconnect_wakes_waiter_without_turning_eof_into_a_receipt() {
        let(sink,peer,_)=pair();register(&sink,&peer,DISPLAY,OBJECT);
        let(child,_nonce)=start_retirement(&sink,&peer,DISPLAY,OBJECT);
        sink.peer_disconnected().unwrap();
        assert!(matches!(child.join().unwrap(),Err(DenialSinkError::PeerDisconnected)));
        let tasks=sink.lock_tasks().unwrap();
        assert!(tasks.peer_disconnected);
        assert!(!tasks.get(&DISPLAY).unwrap().retirement.as_ref().unwrap().receipt_received);
    }

    #[test]
    fn failed_retire_send_preserves_attempt_and_primary_without_resending() {
        let(sink,peer,_)=pair();register(&sink,&peer,DISPLAY,OBJECT);drop(peer);
        assert!(matches!(sink.unregister_task(DISPLAY,OBJECT),Err(DenialSinkError::Ipc(_))));
        let nonce={
            let tasks=sink.lock_tasks().unwrap();
            let request=tasks.get(&DISPLAY).unwrap().retirement.as_ref().unwrap();
            assert!(request.send_attempted&&request.send_error.is_some()&&!request.receipt_received);
            request.nonce
        };
        assert!(matches!(sink.unregister_task(DISPLAY,OBJECT),
            Err(DenialSinkError::RetirementPending{nonce:actual,..}) if actual==nonce));
        assert_eq!(sink.lock_tasks().unwrap().next_nonce,nonce.0);
    }

    #[test]
    fn receipt_with_accepted_frames_outstanding_is_rejected_without_erasure() {
        let(sink,peer,_)=pair();register(&sink,&peer,DISPLAY,OBJECT);
        {
            let mut tasks=sink.lock_tasks().unwrap();let task=tasks.get_mut(&DISPLAY).unwrap();
            task.frame_targets.insert(FrameId(1),BufferId(11));
            task.render_targets.insert(BufferId(11),target(11,false,true));
        }
        let(child,nonce)=start_retirement(&sink,&peer,DISPLAY,OBJECT);
        assert!(matches!(receive_ack(&sink,&peer,OBJECT,nonce),Err(DenialSinkError::RetirementFramesOutstanding(OBJECT))));
        assert_eq!(sink.lock_tasks().unwrap().get(&DISPLAY).unwrap().frame_targets.len(),1);
        sink.peer_disconnected().unwrap();
        assert!(matches!(child.join().unwrap(),Err(DenialSinkError::PeerDisconnected)));
    }

    #[test]
    fn local_reservation_survives_receipt_until_real_cancel_path_wakes_waiter() {
        let(sink,peer,_)=pair();register(&sink,&peer,DISPLAY,OBJECT);
        sink.lock_tasks().unwrap().get_mut(&DISPLAY).unwrap().render_targets.insert(BufferId(11),target(11,true,false));
        let(child,nonce)=start_retirement(&sink,&peer,DISPLAY,OBJECT);
        receive_ack(&sink,&peer,OBJECT,nonce).unwrap();
        assert!(!child.is_finished());
        assert!(sink.lock_tasks().unwrap().contains_key(&DISPLAY));
        sink.cancel_reserved_target(DISPLAY,BufferId(11));
        child.join().unwrap().unwrap();
    }

    #[test]
    fn duplicate_receipt_does_not_upgrade_or_erase_reserved_local_resources() {
        let(sink,peer,_)=pair();register(&sink,&peer,DISPLAY,OBJECT);
        sink.lock_tasks().unwrap().get_mut(&DISPLAY).unwrap().render_targets.insert(BufferId(11),target(11,true,false));
        let(child,nonce)=start_retirement(&sink,&peer,DISPLAY,OBJECT);
        receive_ack(&sink,&peer,OBJECT,nonce).unwrap();
        assert!(matches!(receive_ack(&sink,&peer,OBJECT,nonce),Err(DenialSinkError::RetirementMismatch{..})));
        assert!(sink.lock_tasks().unwrap().get(&DISPLAY).unwrap().render_targets.get(&BufferId(11)).unwrap().reserved);
        sink.cancel_reserved_target(DISPLAY,BufferId(11));
        child.join().unwrap().unwrap();
    }

    #[test]
    fn retirement_rejects_new_binding_activation_target_and_layer_work() {
        let(sink,peer,_)=pair();register(&sink,&peer,DISPLAY,OBJECT);
        let(child,nonce)=start_retirement(&sink,&peer,DISPLAY,OBJECT);
        assert!(matches!(sink.bind_task(DISPLAY,TaskId(42)),Err(DenialSinkError::TaskRetiring(DISPLAY))));
        assert!(matches!(sink.request_activation(DISPLAY),Err(DenialSinkError::TaskRetiring(DISPLAY))));
        assert!(matches!(sink.acquire_surfaceflinger_target(DISPLAY),Err(DenialSinkError::TaskRetiring(DISPLAY))));
        assert!(matches!(sink.bind_layer_stream(DISPLAY,&[]),Err(DenialSinkError::TaskRetiring(DISPLAY))));
        let mut clone=sink.clone();
        assert!(matches!(crate::minigbm::PresentationSink::acquire_target(&mut clone,DISPLAY),Err(ErrorCode::NoResources)));
        no_wire(&peer);
        receive_ack(&sink,&peer,OBJECT,nonce).unwrap();
        child.join().unwrap().unwrap();
    }

    #[test]
    fn partial_registration_rejects_live_work_until_explicit_retirement() {
        let(sink,peer,device)=pair();
        *device.seam.close_peer_on_descriptor_borrow.lock().unwrap()=Some(peer);
        assert!(sink.register_task(OBJECT,&reservation(DISPLAY)).is_err());
        assert!(matches!(sink.bind_task(DISPLAY,TaskId(42)),Err(DenialSinkError::RegistrationIncomplete(DISPLAY))));
        assert!(matches!(sink.request_activation(DISPLAY),Err(DenialSinkError::RegistrationIncomplete(DISPLAY))));
        assert!(matches!(sink.acquire_surfaceflinger_target(DISPLAY),Err(DenialSinkError::RegistrationIncomplete(DISPLAY))));
        assert!(sink.suppress_task_metadata(OBJECT).unwrap());
    }

    #[test]
    fn late_target_metadata_does_not_replace_retirement_resource_accounting() {
        let(sink,peer,_)=pair();register(&sink,&peer,DISPLAY,OBJECT);
        sink.lock_tasks().unwrap().get_mut(&DISPLAY).unwrap().render_targets.insert(BufferId(11),target(11,true,false));
        let(child,nonce)=start_retirement(&sink,&peer,DISPLAY,OBJECT);
        let descriptor=AttachedDescriptor{kind:DescriptorKind::DmabufPlane,
            fd:std::fs::File::open("/dev/null").unwrap().into()};
        sink.register_render_target(OBJECT,5,metadata(12),vec![descriptor]).unwrap();
        sink.unregister_render_target(OBJECT,BufferId(11)).unwrap();
        {
            let tasks=sink.lock_tasks().unwrap();let task=tasks.get(&DISPLAY).unwrap();
            assert_eq!(task.render_targets.len(),1);
            assert!(task.render_targets.get(&BufferId(11)).unwrap().reserved);
        }
        receive_ack(&sink,&peer,OBJECT,nonce).unwrap();
        sink.cancel_reserved_target(DISPLAY,BufferId(11));
        child.join().unwrap().unwrap();
    }

    #[test]
    fn late_configure_cannot_send_after_retire_or_publish_new_session_state() {
        let(sink,peer,_)=pair();register(&sink,&peer,DISPLAY,OBJECT);
        let(child,nonce)=start_retirement(&sink,&peer,DISPLAY,OBJECT);
        let mut session=Session::default();
        let message=DenialMessage::Configure{object:OBJECT,serial:9,width:800,height:600,
            scale_numerator:1,scale_denominator:1,transform:Transform::Normal,refresh_millihz:60_000};
        assert!(matches!(sink.apply_task_event(&mut session,&message),Err(DenialSinkError::TaskRetiring(DISPLAY))));
        sink.acknowledge_configure(&mut session,DISPLAY,9).unwrap();
        assert!(sink.suppress_task_metadata(OBJECT).unwrap());
        no_wire(&peer);
        receive_ack(&sink,&peer,OBJECT,nonce).unwrap();
        child.join().unwrap().unwrap();
    }

    #[test]
    fn same_object_later_registration_rejects_previous_retirement_receipt() {
        let(sink,peer,_)=pair();register(&sink,&peer,DISPLAY,OBJECT);
        let(first,old_nonce)=start_retirement(&sink,&peer,DISPLAY,OBJECT);
        receive_ack(&sink,&peer,OBJECT,old_nonce).unwrap();first.join().unwrap().unwrap();
        let new_display=DisplayId(10);
        register(&sink,&peer,new_display,OBJECT);
        let(second,new_nonce)=start_retirement(&sink,&peer,new_display,OBJECT);
        assert!(new_nonce.0>old_nonce.0);
        assert!(matches!(receive_ack(&sink,&peer,OBJECT,old_nonce),Err(DenialSinkError::RetirementMismatch{..})));
        assert!(sink.lock_tasks().unwrap().contains_key(&new_display));
        receive_ack(&sink,&peer,OBJECT,new_nonce).unwrap();second.join().unwrap().unwrap();
    }

    #[test]
    fn real_core_release_path_drains_a_retiring_accepted_frame_before_receipt() {
        let(sink,peer,_)=pair();register(&sink,&peer,DISPLAY,OBJECT);
        let mut session=Session::default();
        session.create_task_window(TaskWindowSpec{task:TaskId(42),display:DISPLAY,package:"org.example.retirement".into()}).unwrap();
        sink.bind_task(DISPLAY,TaskId(42)).unwrap();let _bind=wire(&peer);
        sink.apply_task_event(&mut session,&DenialMessage::FormatFeedback{
            object:OBJECT,generation:1,formats:vec![metadata(11).format]}).unwrap();
        sink.apply_task_event(&mut session,&DenialMessage::Configure{
            object:OBJECT,serial:5,width:800,height:600,scale_numerator:1,scale_denominator:1,
            transform:Transform::Normal,refresh_millihz:60_000}).unwrap();
        sink.acknowledge_configure(&mut session,DISPLAY,5).unwrap();let _ack=wire(&peer);
        let composer=session.windows_mut().composer_for_display_mut(DISPLAY).unwrap();
        composer.set_power_mode(DISPLAY,PowerMode::On).unwrap();
        composer.create_layer(DISPLAY,LayerState{id:LayerId(1),requested_composition:Composition::Client,
            z:0,protected_content:false}).unwrap();
        composer.validate_display(DISPLAY).unwrap();composer.accept_display_changes(DISPLAY).unwrap();
        composer.set_client_target(DISPLAY,ClientTarget{buffer:metadata(11),
            damage:Vec::<Damage>::new(),has_acquire_fence:true}).unwrap();
        let frame=composer.present_display(DISPLAY).unwrap().frame;
        let release_point={
            let mut tasks=sink.lock_tasks().unwrap();let task=tasks.get_mut(&DISPLAY).unwrap();
            let prepared=task.binding.prepare_present(DISPLAY,&frame).unwrap();
            // Prior accepted render ownership is explicit fixture input. No GPU runs.
            task.render_targets.insert(BufferId(11),target(11,false,true));
            task.frame_targets.insert(frame.frame_id,BufferId(11));
            prepared.release_point
        };
        let(child,nonce)=start_retirement(&sink,&peer,DISPLAY,OBJECT);
        let release=DenialMessage::BufferReleased{object:OBJECT,frame:frame.frame_id,buffer:BufferId(11),release_point};
        assert!(matches!(sink.apply_task_event(&mut session,&release).unwrap(),AppliedDenialEvent::BufferReleased(_)));
        assert_eq!(session.windows().composer_for_display(DISPLAY).unwrap().in_flight_count(),0);
        receive_ack(&sink,&peer,OBJECT,nonce).unwrap();child.join().unwrap().unwrap();
    }
}
