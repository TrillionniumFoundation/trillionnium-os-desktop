import com.android.calendar.alerts.AlertIdentity;
public final class AlertIdentityTest {
    static int checks;
    static void check(boolean value,String label){checks++;if(!value)throw new AssertionError(label);}
    public static void main(String[] args) {
        String old=AlertIdentity.key(1,4,1000,2000,900,800,10);
        check(old.equals(AlertIdentity.key(1,4,1000,2000,900,800,10)),"same exact alert remains stable");
        check(!old.equals(AlertIdentity.key(1,5,1000,2000,900,800,10)),"reused row ID for another event differs");
        check(!old.equals(AlertIdentity.key(1,4,1001,2000,900,800,10)),"another occurrence begin differs");
        check(!old.equals(AlertIdentity.key(1,4,1000,2001,900,800,10)),"changed occurrence end differs");
        check(!old.equals(AlertIdentity.key(1,4,1000,2000,901,800,10)),"another due time differs");
        check(!old.equals(AlertIdentity.key(1,4,1000,2000,900,801,10)),"recreated row creation identity differs");
        check(!old.equals(AlertIdentity.key(1,4,1000,2000,900,800,15)),"another reminder definition differs");
        check(!old.equals(AlertIdentity.key(4294967296L,4,1000,2000,900,800,10)),"request-code collision cannot merge full identity");
        check(!AlertIdentity.key(1,23,4,5,6,7,8).equals(AlertIdentity.key(12,3,4,5,6,7,8)),"numeric fields cannot concatenate ambiguously");
        System.out.println("AlertIdentityTest: "+checks+" checks passed");
    }
}
