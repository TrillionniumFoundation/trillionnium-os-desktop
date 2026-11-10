# ACT-2 destination fence candidate

Base companion: `fd8d56c52b971c2d5d0e6430f296803b43ef60a3`, tree `347fbb7e9931006c749b5bef0e1550c54bc08f27`.

A fence is a separately authorized effect. It is not accepted on the read-only recovery lane. Under the same serialized worker as edits, matching the original expected revision advances the durable document revision without applying the original text. Subsequent old-revision requests are refused. If the original edit already won, cancellation is not reported as successful. Original/cancel identity and payload bindings remain distinct.

The destination keeps one shared pending receipt capacity, exact receipt retirement and checkpoint compatibility. Legacy v1/v2 checkpoints still read; a document enters v3 when it uses a fence and remains v3 after retirement. Tests cover fence-first/late-original, apply-first, wrong retirement, checkpoint corruption and actual filesystem restore. The new worker route uses the original private effect endpoint; it does not add an effect to the recovery channel.

The dedicated workflow tests the entire core (including legacy goldens), the original App worker, locked Session/App builds, scoped lint and official formatter. Exact source/lock/binary identities, logs and formatter postimages are retained. This is an uncompiled candidate until actual workflow results are read.

This stage does not settle an original Hepta operation merely because a cancel operation committed. The source responsibility proof, complete real App/owner integration, full DynamicToolCall human/Root authorization chain, production activation and skill-learning benefit are separate gates. No deployment or main merge is included.
